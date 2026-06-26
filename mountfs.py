#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 Kjell Kristian Grane Torgersen
"""Mount a remote DOS machine's filesystem locally over the serial link (FUSE).

The serial link is slow, so a background thread breadth-first crawls *all*
directory metadata into an in-memory tree at startup — after that `ls`/`stat`
are instant.  File contents are fetched on demand with the v2 ranged-read packet
(`pread`) and written through with ranged-write (`pwrite`); delete/rename/rmdir
use the other v2 packets.  This is safe to cache because the DOS box is
single-tasking and *only this program* mutates it while mounted, so the cache
stays authoritative.

    python3 mountfs.py --tcp 127.0.0.1:4555 /mnt/dos --root 'C:\\'

Needs the XFER.COM agent (built from xfercom.asm) and, to actually mount, `fusepy`
(`pip install fusepy`).  The cache/Link layer (`RemoteFS`) imports no FUSE and is
unit-tested headless in test_com.py.
"""

from __future__ import annotations

import argparse
import errno
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fuse import Operations

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import host  # noqa: E402


class Node:
    __slots__ = ("attr", "children", "is_dir", "listed", "name", "size")

    def __init__(self, name: str, is_dir: bool, size: int = 0, attr: int = 0) -> None:
        self.name = name
        self.is_dir = is_dir
        self.size = size
        self.attr = attr
        self.children: dict[str, Node] | None = {} if is_dir else None
        self.listed = False  # dirs: has the child list been fetched yet?


class RemoteFS:
    """In-memory metadata cache + write-through content I/O over a `host.Link`.

    All link traffic is serialised by `iolock` (single serial channel); the cache
    tree is guarded by `clock`.  The two are never held nested, so cache-hit
    lookups never wait on a slow transfer."""

    def __init__(self, link: host.Link, root: str = "C:\\") -> None:
        self.link = link
        self.iolock = threading.Lock()
        self.clock = threading.RLock()
        r = root.replace("/", "\\")
        if r.endswith(":"):
            r += "\\"  # bare drive -> its root
        self.root = r or "\\"
        self.tree = Node("", True)
        self._queue: deque[tuple[Node, str]] = deque()
        self._crawler: threading.Thread | None = None
        self._stop = False

    # --- DOS path helpers ---------------------------------------------------
    @staticmethod
    def _join(dp: str, name: str) -> str:
        return (dp + name) if dp.endswith("\\") else (dp + "\\" + name)

    @staticmethod
    def _listspec(dp: str) -> str:
        return (dp + "*.*") if dp.endswith("\\") else (dp + "\\*.*")

    @staticmethod
    def _split(path: str) -> tuple[str, str]:
        path = path.rstrip("/")
        parent, _, name = path.rpartition("/")
        return (parent or "/"), name.upper()

    # --- crawling / resolution ---------------------------------------------
    def start(self) -> None:
        self._ensure_listed(self.tree, self.root)  # root first (so '/' works)
        self._crawler = threading.Thread(target=self._crawl, daemon=True)
        self._crawler.start()

    def _crawl(self) -> None:
        while not self._stop:
            with self.clock:
                if not self._queue:
                    return
                node, dp = self._queue.popleft()
            self._ensure_listed(node, dp)

    def _ensure_listed(self, node: Node, dp: str) -> None:
        with self.clock:
            if node.listed:
                return
        with self.iolock:
            entries = self.link.list_dir(self._listspec(dp))
        with self.clock:
            if node.listed:
                return
            for name, attr, size in entries:
                if name in (".", ".."):
                    continue
                child = Node(name, bool(attr & 0x10), size, attr)
                node.children[name] = child
                if child.is_dir:
                    self._queue.append((child, self._join(dp, name)))
            node.listed = True

    def resolve(self, path: str) -> tuple[Node, str] | None:
        """Return (node, dospath) for a POSIX path, listing ancestors as needed."""
        node, dp = self.tree, self.root
        self._ensure_listed(node, dp)
        for part in (p.upper() for p in path.split("/") if p):
            with self.clock:
                child = node.children.get(part) if node.children else None
            if child is None:
                return None
            node, dp = child, self._join(dp, part)
            if node.is_dir:
                self._ensure_listed(node, dp)
        return node, dp

    def _parent_dir(self, path: str) -> tuple[Node, str, str]:
        parent, name = self._split(path)
        res = self.resolve(parent)
        if res is None or not res[0].is_dir:
            raise FileNotFoundError(parent)
        return res[0], res[1], name

    # --- operations (used by the FUSE layer and by tests) -------------------
    def getattr(self, path: str) -> Node:
        res = self.resolve(path)
        if res is None:
            raise FileNotFoundError(path)
        return res[0]

    def readdir(self, path: str) -> list[str]:
        res = self.resolve(path)
        if res is None or not res[0].is_dir:
            raise FileNotFoundError(path)
        node, dp = res
        self._ensure_listed(node, dp)
        with self.clock:
            return list(node.children.keys())

    def read(self, path: str, size: int, offset: int) -> bytes:
        res = self.resolve(path)
        if res is None or res[0].is_dir:
            raise FileNotFoundError(path)
        with self.iolock:
            return self.link.pread(res[1], offset, size)

    def write(self, path: str, data: bytes, offset: int) -> int:
        res = self.resolve(path)
        if res is None or res[0].is_dir:
            raise FileNotFoundError(path)
        node, dp = res
        with self.iolock:
            self.link.pwrite(dp, offset, data)
        with self.clock:
            node.size = max(node.size, offset + len(data))
        return len(data)

    def truncate(self, path: str, length: int) -> None:
        res = self.resolve(path)
        if res is None or res[0].is_dir:
            raise FileNotFoundError(path)
        node, dp = res
        with self.iolock:
            self.link.truncate(dp, length)
        with self.clock:
            node.size = length

    def create(self, path: str) -> None:
        parent, pdp, name = self._parent_dir(path)
        dp = self._join(pdp, name)
        with self.iolock:
            self.link.create_empty(dp)
        with self.clock:
            parent.children[name] = Node(name, False, 0, 0x20)

    def unlink(self, path: str) -> None:
        parent, pdp, name = self._parent_dir(path)
        with self.iolock:
            self.link.delete(self._join(pdp, name))
        with self.clock:
            parent.children.pop(name, None)

    def mkdir(self, path: str) -> None:
        parent, pdp, name = self._parent_dir(path)
        with self.iolock:
            self.link.mkdir(self._join(pdp, name))
        with self.clock:
            node = Node(name, True, 0, 0x10)
            node.listed = True  # brand new -> empty, nothing to crawl
            parent.children[name] = node

    def rmdir(self, path: str) -> None:
        parent, pdp, name = self._parent_dir(path)
        with self.iolock:
            self.link.rmdir(self._join(pdp, name))
        with self.clock:
            parent.children.pop(name, None)

    def rename(self, old: str, new: str) -> None:
        res = self.resolve(old)
        if res is None:
            raise FileNotFoundError(old)
        old_node, old_dp = res
        nparent, npdp, nname = self._parent_dir(new)
        new_dp = self._join(npdp, nname)
        with self.iolock:
            self.link.rename(old_dp, new_dp)
        with self.clock:
            op, oname = self._split(old)
            oparent = self.resolve(op)[0]
            oparent.children.pop(oname, None)
            old_node.name = nname
            nparent.children[nname] = old_node


# ---------------------------------------------------------------------------
# FUSE binding (only imported when actually mounting)
# ---------------------------------------------------------------------------
def _build_fuse_ops(rfs: RemoteFS) -> Operations:
    import os

    from fuse import FuseOSError, Operations

    now = time.time()
    uid, gid = os.getuid(), os.getgid()

    class DosFuse(Operations):
        def _attr(self, node: Node) -> dict[str, int | float]:
            mode = (0o040000 | 0o755) if node.is_dir else (0o100000 | 0o644)
            return {
                "st_mode": mode,
                "st_nlink": 2 if node.is_dir else 1,
                "st_size": node.size,
                "st_ctime": now,
                "st_mtime": now,
                "st_atime": now,
                "st_uid": uid,
                "st_gid": gid,
            }

        def getattr(self, path: str, fh: int | None = None) -> dict[str, int | float]:
            try:
                return self._attr(rfs.getattr(path))
            except FileNotFoundError:
                raise FuseOSError(errno.ENOENT) from None

        def readdir(self, path: str, fh: int) -> list[str]:
            try:
                return [".", "..", *rfs.readdir(path)]
            except FileNotFoundError:
                raise FuseOSError(errno.ENOENT) from None

        def read(self, path: str, size: int, offset: int, fh: int) -> bytes:
            return rfs.read(path, size, offset)

        def write(self, path: str, data: bytes, offset: int, fh: int) -> int:
            return rfs.write(path, data, offset)

        def truncate(self, path: str, length: int, fh: int | None = None) -> None:
            rfs.truncate(path, length)

        def create(self, path: str, mode: int, fi: object = None) -> int:
            rfs.create(path)
            return 0

        def open(self, path: str, flags: int) -> int:
            return 0

        def unlink(self, path: str) -> None:
            rfs.unlink(path)

        def mkdir(self, path: str, mode: int) -> None:
            rfs.mkdir(path)

        def rmdir(self, path: str) -> None:
            rfs.rmdir(path)

        def rename(self, old: str, new: str) -> None:
            rfs.rename(old, new)

        # no-ops: DOS has no perms/owners and timestamps aren't exposed
        def chmod(self, path: str, mode: int) -> int:
            return 0

        def chown(self, path: str, uid: int, gid: int) -> int:
            return 0

        def utimens(self, path: str, times: tuple[float, float] | None = None) -> int:
            return 0

        def flush(self, path: str, fh: int) -> int:
            return 0

        def release(self, path: str, fh: int) -> int:
            return 0

        def destroy(self, private_data: object) -> None:
            with rfs.iolock:
                rfs.link.quit()

    return DosFuse()


def _make_transport(
    args: argparse.Namespace,
) -> host.SocketTransport | host.SerialTransport:
    if args.socket:
        return host.SocketTransport.unix(args.socket)
    if args.tcp:
        h, _, p = args.tcp.rpartition(":")
        return host.SocketTransport.tcp(h, int(p))
    if args.port:
        return host.SerialTransport(args.port, args.baud)
    sys.exit("one of --port / --socket / --tcp is required")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="mount a remote DOS FS over serial")
    ap.add_argument("--port", help="real serial device, e.g. /dev/ttyUSB0")
    ap.add_argument("--socket", help="emulator serial as a Unix socket")
    ap.add_argument("--tcp", help="emulator serial as host:port")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("mountpoint")
    ap.add_argument("--root", default="C:\\", help="remote base path (default C:\\)")
    args = ap.parse_args(argv)

    link = host.Link(_make_transport(args))
    rfs = RemoteFS(link, args.root)
    print(f"crawling {args.root} ...", flush=True)
    rfs.start()

    from fuse import FUSE

    # Runs in the foreground until unmounted (fusermount -u <mountpoint>), which
    # tells the agent to quit via the destroy() callback.
    FUSE(_build_fuse_ops(rfs), args.mountpoint, foreground=True, nothreads=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
