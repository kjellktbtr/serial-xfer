#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 Kjell Kristian Grane Torgersen
"""Host side of the serial file-transfer protocol.

Talks to the DOS agent (the XFER.COM built from xfercom.asm) over a byte stream
(a real serial port, or an emulator's Unix/TCP socket).  Provides:
  * COBS framing + CRC-16/CCITT
  * an ack/nak send-and-wait link
  * DOS 8.3 upper-case filename mangling with Windows-9x "~N" collision avoidance
  * recursive directory upload and single-file download

Wire format (see PROTOCOL.md / xfercom.asm):
  frame  = COBS(packet) + 0x00
  packet = TYPE(1) SEQ(1) DATA(..) CRC16(2 big-endian over TYPE+SEQ+DATA)
"""

from __future__ import annotations

import contextlib
import socket
import sys
import time
import zlib
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, Self

if TYPE_CHECKING:
    from collections.abc import Callable

try:
    from tqdm import tqdm  # optional: progress bars
except ImportError:  # pragma: no cover
    tqdm = None


class Transport(Protocol):
    """Byte-stream endpoint the `Link` drives (serial port or emulator socket)."""

    def send(self, data: bytes) -> None: ...
    def read_until(self, term: bytes, timeout: float = ...) -> bytes: ...


T_OPEN, T_DATA, T_CLOSE, T_QUIT, T_GET = 1, 2, 3, 4, 5
T_MKDIR, T_LIST, T_ENTRY, T_MSG = 6, 7, 8, 9
T_DEL, T_RMD, T_REN, T_PREAD, T_PWRITE = 10, 11, 12, 13, 14  # protocol v2
T_RAW = 15  # print DATA verbatim on the target (host owns the line endings)
T_ACK, T_NAK = 0x10, 0x11

CHUNK = 128  # file bytes per DATA packet (also the v2 pread/pwrite span)

# Transfer-time estimate: 9600 baud 8N1 = 960 B/s raw; COBS/CRC/ACK/turnaround
# overhead drops the effective rate to ~800 B/s.
EFFECTIVE_BPS = 800
PER_FILE_OVERHEAD_S = 0.5  # OPEN/MKDIR/CLOSE handshakes per file
SCREEN_W = 80
LINE_W = SCREEN_W - 1  # stay one short of 80 so the live line never auto-wraps


def est_secs(size: int) -> float:
    return size / EFFECTIVE_BPS + PER_FILE_OVERHEAD_S


def fmt_dur(secs: float) -> str:
    secs = int(secs + 0.5)
    return f"{secs // 60}:{secs % 60:02d}"


def middle_truncate(s: str, width: int) -> str:
    """Shorten `s` to `width` chars, eliding the middle with '...'."""
    if len(s) <= width:
        return s
    if width <= 3:
        return s[:width]
    keep = width - 3
    left = (keep + 1) // 2
    right = keep - left
    return s[:left] + "..." + (s[-right:] if right else "")


NAME_W = 42  # filename+path field on the live line


def progress_line(name: str, size: int, done_bytes: int, total_bytes: int) -> str:
    """A fixed `LINE_W`-char status line for the target screen:
    name+path (NAME_W, middle-elided) | size in k | total ETA as M:SS | a [bar]
    with the total percentage centred in it."""
    pct = (100.0 * done_bytes / total_bytes) if total_bytes else 100.0
    eta = max(0.0, (total_bytes - done_bytes) / EFFECTIVE_BPS)
    kb = round(size / 1024)
    prefix = f"{middle_truncate(name, NAME_W):<{NAME_W}} {kb:>5}k {fmt_dur(eta):>7} "
    bar_w = max(8, LINE_W - len(prefix))
    inner = bar_w - 2
    filled = round(pct / 100.0 * inner)
    bar = list("#" * filled + " " * (inner - filled))
    pct_s = f"{pct:.0f}%"
    start = max(0, (inner - len(pct_s)) // 2)
    bar[start : start + len(pct_s)] = list(pct_s)
    line = prefix + "[" + "".join(bar)[:inner] + "]"
    return line[:LINE_W].ljust(LINE_W)


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def crc32_be(crc: int) -> bytes:
    return bytes(
        [(crc >> 24) & 0xFF, (crc >> 16) & 0xFF, (crc >> 8) & 0xFF, crc & 0xFF]
    )


# ---------------------------------------------------------------------------
# COBS + CRC
# ---------------------------------------------------------------------------
def cobs_encode(data: bytes) -> bytes:
    out = bytearray()
    code_i = 0
    out.append(0)  # placeholder for first code
    code = 1
    for b in data:
        if b == 0:
            out[code_i] = code
            code_i = len(out)
            out.append(0)
            code = 1
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_i] = code
                code_i = len(out)
                out.append(0)
                code = 1
    out[code_i] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    out = bytearray()
    rp = 0
    n = len(data)
    while rp < n:
        code = data[rp]
        rp += 1
        for _ in range(1, code):
            if rp < n:
                out.append(data[rp])
                rp += 1
        if code < 0xFF and rp < n:
            out.append(0)
    return bytes(out)


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = (
                ((crc << 1) ^ 0x1021) & 0xFFFF
                if (crc & 0x8000)
                else (crc << 1) & 0xFFFF
            )
    return crc & 0xFFFF


def make_frame(ptype: int, seq: int, data: bytes = b"") -> bytes:
    pkt = bytes([ptype, seq]) + data
    crc = crc16(pkt)
    pkt += bytes([(crc >> 8) & 0xFF, crc & 0xFF])
    return cobs_encode(pkt) + b"\x00"


def parse_packet(frame_no_delim: bytes) -> tuple[int, int, bytes] | None:
    """Return (type, seq, data) or None if CRC/length is bad."""
    pkt = cobs_decode(frame_no_delim)
    if len(pkt) < 4:
        return None
    body, got = pkt[:-2], (pkt[-2] << 8) | pkt[-1]
    if crc16(body) != got:
        return None
    return body[0], body[1], body[2:]


# ---------------------------------------------------------------------------
# DOS 8.3 filename mangling (upper-case + Windows-9x ~N collision avoidance)
# ---------------------------------------------------------------------------
_OK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&'()-@^_`{}~")


def _clean(part: str) -> str:
    return "".join(c if c.upper() in _OK else "_" for c in part.upper())


def to_83(name: str, taken: set[str]) -> str:
    """Map an arbitrary filename to a unique upper-case DOS 8.3 name.

    `taken` is the set of names already used in the target directory; the
    chosen name is added to it.  Long/colliding names get a `~N` numeric tail
    exactly like Windows 9x short-name generation.
    """
    # Windows uses the last dot for the extension; a name that is only dots
    # (or has no interior dot) has no extension.
    if "." in name.strip("."):
        raw_base, _, raw_ext = name.rpartition(".")
    else:
        raw_base, raw_ext = name, ""
    ext = _clean(raw_ext)[:3]
    base = _clean(raw_base) or "_"

    def assemble(b: str) -> str:
        return f"{b}.{ext}" if ext else b

    cand = assemble(base[:8])
    if len(base) <= 8 and cand not in taken:
        taken.add(cand)
        return cand
    # Need shortening / disambiguation: BASE~N.EXT
    n = 1
    while True:
        tail = f"~{n}"
        cand = assemble(base[: 8 - len(tail)] + tail)
        if cand not in taken:
            taken.add(cand)
            return cand
        n += 1


# ---------------------------------------------------------------------------
# Transfer jobs + report
# ---------------------------------------------------------------------------
class _Job:
    """One file to move; carries its retry state so it can be requeued."""

    def __init__(
        self, kind: str, local: Path, dos_path: str, size: int | None = None
    ) -> None:
        self.kind = kind  # "up" or "down"
        self.local = Path(local)
        self.dos_path = dos_path
        self.size = size  # bytes, if known up front (for the summary/estimate)
        self.attempts = 0
        self.last_error: str | None = None

    @property
    def label(self) -> str:
        return (
            f"{self.local} -> {self.dos_path}"
            if self.kind == "up"
            else f"{self.dos_path} -> {self.local}"
        )

    def run(
        self, link: Link, on_chunk: Callable[[int], None] | None = None
    ) -> tuple[int, float]:
        t0 = time.monotonic()
        if self.kind == "up":
            n = link.upload_file_once(self.local, self.dos_path, on_chunk)
        else:
            n = link.download_file_once(self.dos_path, self.local, on_chunk)
        return n, time.monotonic() - t0


class TransferReport:
    """Collects per-file results and renders a human-readable report."""

    def __init__(self) -> None:
        self.ok: list[tuple[_Job, int, float]] = []
        self.pending: list[_Job] = []

    def record_ok(self, job: _Job, nbytes: int, secs: float) -> None:
        self.ok.append((job, nbytes, secs))

    def record_pending(self, jobs: list[_Job]) -> None:
        self.pending = list(jobs)

    def render(self) -> str:
        lines = [
            "=== transfer report ===",
            f"{'file -> target':52} {'bytes':>9} {'time':>7} {'KB/s':>7} {'try':>3}",
        ]
        tot_b = tot_t = 0.0
        for job, nbytes, secs in self.ok:
            kbs = (nbytes / secs / 1024.0) if secs > 0 else 0.0
            tot_b += nbytes
            tot_t += secs
            lines.append(
                f"{job.label[:52]:52} {nbytes:>9} {secs:>6.2f}s {kbs:>7.1f} "
                f"{job.attempts + 1:>3}"
            )
        ov = (tot_b / tot_t / 1024.0) if tot_t > 0 else 0.0
        lines.append(
            f"  totals: {len(self.ok)} ok, {int(tot_b)} bytes, {tot_t:.2f}s, "
            f"{ov:.1f} KB/s avg"
        )
        if self.pending:
            lines.append(f"  PENDING (interrupted, {len(self.pending)} not completed):")
            lines.extend(
                f"    {job.label[:60]:60} tries={job.attempts} "
                f"last_error={job.last_error}"
                for job in self.pending
            )
        lines.append("  renamed target structure:")
        lines.extend(f"    {job.local}  ->  {job.dos_path}" for job, _, _ in self.ok)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Link: send a packet, wait for ACK<seq> (resend on NAK / timeout)
# ---------------------------------------------------------------------------
class Link:
    def __init__(
        self, transport: Transport, retries: int = 5, timeout: float = 3.0
    ) -> None:
        self.t = transport
        self.retries = retries
        self.timeout = timeout
        self.seq = 0

    def _read_frame(self) -> bytes | None:
        raw = self.t.read_until(b"\x00", timeout=self.timeout)
        if not raw.endswith(b"\x00"):
            return None
        return raw[:-1]

    def xact(self, ptype: int, data: bytes = b"") -> bytes:
        """Send one packet and wait for its ACK; returns the ack data (or raises)."""
        seq = self.seq & 0xFF
        frame = make_frame(ptype, seq, data)
        for _ in range(self.retries):
            self.t.send(frame)
            resp = self._read_frame()
            if resp is None:
                continue
            parsed = parse_packet(resp)
            if parsed is None:
                continue
            rtype, rseq, rdata = parsed
            if rtype == T_ACK and rseq == seq:
                self.seq += 1
                return rdata
            # NAK or stale ack -> resend
        raise OSError(f"no ACK for packet type {ptype} seq {seq}")

    def mkdir(self, dos_path: str) -> None:
        self.xact(T_MKDIR, dos_path.encode("ascii"))

    def message(self, text: str) -> None:
        """Show `text` on the DOS target's screen (the agent just prints it)."""
        self.xact(T_MSG, text.encode("ascii", "replace")[:120])

    def raw(self, data: bytes) -> None:
        """Print `data` verbatim on the target (host owns the line endings)."""
        self.xact(T_RAW, data[: SCREEN_W + 2])

    # --- protocol v2: delete / rename / byte-range I/O ----------------------
    @staticmethod
    def _status_ok(ack: bytes) -> bool:
        return not ack or ack[0] == 0

    def delete(self, path: str) -> None:
        if not self._status_ok(self.xact(T_DEL, path.encode("ascii"))):
            raise OSError(f"delete failed: {path}")

    def rmdir(self, path: str) -> None:
        if not self._status_ok(self.xact(T_RMD, path.encode("ascii"))):
            raise OSError(f"rmdir failed: {path}")

    def rename(self, old: str, new: str) -> None:
        payload = old.encode("ascii") + b"\x00" + new.encode("ascii")
        if not self._status_ok(self.xact(T_REN, payload)):
            raise OSError(f"rename failed: {old} -> {new}")

    def pread(self, path: str, offset: int, length: int) -> bytes:
        """Read `length` bytes from `offset`, looping ≤CHUNK-byte spans; a short
        or empty reply means EOF."""
        name = path.encode("ascii")
        out = bytearray()
        while len(out) < length:
            want = min(CHUNK, length - len(out))
            off = offset + len(out)
            req = off.to_bytes(4, "little") + want.to_bytes(2, "little") + name
            data = self.xact(T_PREAD, req)
            out += data
            if len(data) < want:  # short read -> EOF
                break
        return bytes(out)

    def pwrite(self, path: str, offset: int, data: bytes) -> int:
        """Write `data` at `offset` in ≤CHUNK-byte spans.  An empty `data` sends a
        single zero-length write, which on DOS sets EOF at `offset`
        (truncate / create-empty)."""
        name = path.encode("ascii")
        i = 0
        while True:
            chunk = data[i : i + CHUNK]
            req = (offset + i).to_bytes(4, "little") + name + b"\x00" + chunk
            if not self._status_ok(self.xact(T_PWRITE, req)):
                raise OSError(f"pwrite failed at {offset + i}: {path}")
            i += len(chunk)
            if i >= len(data):
                break
        return len(data)

    def truncate(self, path: str, length: int) -> None:
        self.pwrite(path, length, b"")

    def create_empty(self, path: str) -> None:
        self.pwrite(path, 0, b"")

    # single-attempt primitives (raise on any failure incl. whole-file CRC) ---
    def upload_file_once(
        self, local: Path, dos_path: str, on_chunk: Callable[[int], None] | None = None
    ) -> int:
        """Upload one file to `dos_path` (back-slash DOS path).  Creates parent
        directories first, then OPEN/DATA*/CLOSE; verifies the whole-file CRC-32
        via the CLOSE-ACK status byte.  Returns bytes sent; raises on mismatch.
        `on_chunk(n)` is called after each DATA packet (for progress bars)."""
        data = Path(local).read_bytes()
        parts = dos_path.split("\\")
        cum = ""
        for p in parts[:-1]:  # mkdir each parent (idempotent)
            cum = (cum + "\\" + p) if cum else p
            self.mkdir(cum)
        self.xact(T_OPEN, dos_path.encode("ascii"))
        for i in range(0, len(data), CHUNK):
            chunk = data[i : i + CHUNK]
            self.xact(T_DATA, chunk)
            if on_chunk:
                on_chunk(len(chunk))
        status = self.xact(T_CLOSE, crc32_be(crc32(data)))
        if not status or status[0] != 0:
            raise OSError(f"whole-file CRC mismatch on {dos_path}")
        return len(data)

    def download_file_once(
        self,
        remote_path: str,
        local: Path,
        on_chunk: Callable[[int], None] | None = None,
    ) -> int:
        """Download one file; verify the whole-file CRC-32 from its CLOSE.
        `on_chunk(n)` is called after each received DATA packet."""
        self.xact(T_GET, remote_path.encode("ascii"))
        out = bytearray()
        expected = None
        while True:
            resp = self._read_frame()
            parsed = parse_packet(resp) if resp else None
            if parsed is None:
                raise OSError(f"timeout/garbage during download of {remote_path}")
            rtype, rseq, rdata = parsed
            if rtype == T_DATA:
                out += rdata
                self.t.send(make_frame(T_ACK, rseq))
                if on_chunk:
                    on_chunk(len(rdata))
            elif rtype == T_CLOSE:
                if len(rdata) >= 4:
                    expected = int.from_bytes(rdata[:4], "big")
                self.t.send(make_frame(T_ACK, rseq))
                break
        if expected is not None and crc32(bytes(out)) != expected:
            raise OSError(f"whole-file CRC mismatch on {remote_path}")
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_bytes(bytes(out))
        return len(out)

    def list_dir(self, spec: str) -> list[tuple[str, int, int]]:
        """Enumerate a DOS directory; returns [(name, attr, size), ...]."""
        self.xact(T_LIST, spec.encode("ascii"))
        out: list[tuple[str, int, int]] = []
        while True:
            resp = self._read_frame()
            parsed = parse_packet(resp) if resp else None
            if parsed is None:
                break
            rtype, rseq, rdata = parsed
            if rtype == T_ENTRY:
                self.t.send(make_frame(T_ACK, rseq))
                attr = rdata[0] if rdata else 0
                size = int.from_bytes(rdata[1:5], "little") if len(rdata) >= 5 else 0
                name = rdata[5:].split(b"\x00")[0].decode("ascii", "replace")
                out.append((name, attr, size))
            elif rtype == T_CLOSE:
                self.t.send(make_frame(T_ACK, rseq))
                break
        return out

    @staticmethod
    def _dir_norm(path: str) -> str:
        """Normalise a user path to a directory prefix: '/'->'\\', a bare drive
        'A:' -> 'A:\\' (root)."""
        p = path.replace("/", "\\")
        if p.endswith(":"):
            p += "\\"
        return p

    def print_dir(self, path: str, recursive: bool = False) -> None:
        """List a remote directory DOS-style (like `dir`, or `dir /s` when
        recursive).  `path` may be '' (current dir), a drive ('A:'), or a path
        ('C:\\DOS'); a spec already containing * / ? is used verbatim."""
        if any(c in path for c in "*?"):
            spec, dir_path = path, path.rsplit("\\", 1)[0] if "\\" in path else ""
            self._dir_one(dir_path, spec, recursive)
            return
        self._dir_one(self._dir_norm(path), None, recursive)

    def _dir_one(self, dir_path: str, spec: str | None, recursive: bool) -> None:
        if spec is None:
            sep = "" if (not dir_path or dir_path.endswith(("\\", ":"))) else "\\"
            spec = f"{dir_path}{sep}*.*"
        print(f"\n Directory of {dir_path or '.'}\n")
        nfiles = nbytes = 0
        subdirs: list[str] = []
        for name, attr, size in self.list_dir(spec):
            if name in (".", ".."):
                continue
            if attr & 0x10:
                print(f"{name:<13}<DIR>")
                join = "" if dir_path.endswith(("\\", ":")) else "\\"
                subdirs.append(f"{dir_path}{join}{name}")
            else:
                print(f"{name:<13}{size:>10}")
                nfiles += 1
                nbytes += size
        print(f"   {nfiles} file(s)  {nbytes} bytes  {len(subdirs)} dir(s)")
        if recursive:
            for sd in subdirs:
                self._dir_one(sd, None, True)

    def _safe_raw(self, data: bytes) -> None:
        """Best-effort verbatim push to the target screen (never fatal)."""
        with contextlib.suppress(OSError):
            self.raw(data)

    def _summary(self, jobs: list[_Job]) -> int:
        """Print the full transfer summary on the host and send a screen-fitted
        copy (≤24 lines, ≤LINE_W chars) to the target.  Returns total bytes."""
        rows = [(str(j.dos_path), j.size) for j in jobs]
        total = sum(sz for _, sz in rows if sz is not None)

        def _sz(sz: int | None) -> tuple[str, str]:
            if sz is None:
                return ("?", "~?")
            return (str(sz), f"~{fmt_dur(est_secs(sz))}")

        print("=== transfer summary ===")
        print(f"{'file':<44}{'bytes':>10}{'est':>8}")
        for name, sz in rows:
            s, e = _sz(sz)
            print(f"{name:<44}{s:>10}{e:>8}")
        print(f"  total: {len(rows)} files, {total} bytes, ~{fmt_dur(est_secs(total))}")

        # Target screen: fixed columns (name 60 | bytes 9 | est 6) = 79 chars, no '~'.
        namew = 60

        def _row(name: str, sz: int | None) -> str:
            s = str(sz) if sz is not None else "?"
            e = fmt_dur(est_secs(sz)) if sz is not None else "?"
            return f"{middle_truncate(name, namew):<{namew}}  {s:>9}  {e:>6}"

        tot_est = fmt_dur(est_secs(total))
        header = f"Transfer: {len(rows)} files, {total} bytes, est {tot_est}"
        lines = [
            middle_truncate(
                header,
                LINE_W,
            ),
            f"{'file':<{namew}}  {'bytes':>9}  {'est':>6}",
        ]
        maxrows = 18
        if len(rows) <= maxrows:
            lines += [_row(n, s) for n, s in rows]
        else:
            head, tail = maxrows // 2, maxrows - maxrows // 2 - 1
            lines += [_row(n, s) for n, s in rows[:head]]
            lines.append(f"  ... ({len(rows) - head - tail} more files) ...")
            lines += [_row(n, s) for n, s in rows[-tail:]]
        for ln in lines:
            self._safe_raw(ln.encode("ascii", "replace") + b"\r\n")
        return total

    # retry-forever driver ----------------------------------------------------
    def run_queue(
        self, jobs: list[_Job], report: TransferReport, progress: bool = True
    ) -> None:
        """Run every job; a failure sends the job to the back of the queue and
        it is retried forever.  Stops when the queue drains or on Ctrl-C, after
        which `report` holds the OK results and any still-pending jobs.  With
        tqdm installed shows an overall bar (files) + a per-file byte bar; the
        agent also displays the current file/result on the target screen."""
        use_bars = progress and tqdm is not None
        say = (
            (lambda s: tqdm.write(s)) if use_bars else (lambda s: print(s, flush=True))
        )
        total_files = len(jobs)
        total_bytes = self._summary(jobs)  # host print + fitted target summary
        done_bytes = 0
        dq: deque[_Job] = deque(jobs)
        done = 0
        overall = (
            tqdm(total=total_files, position=0, unit="file", desc="overall", leave=True)
            if use_bars
            else None
        )
        try:
            while dq:
                job = dq.popleft()
                fbar = None
                if use_bars:
                    fbar = tqdm(
                        total=job.size,  # may be None (single download) -> count-up
                        position=1,
                        unit="B",
                        unit_scale=True,
                        leave=False,
                        desc=str(job.dos_path).rsplit("\\", 1)[-1],
                    )
                # NB: `if fbar` would call tqdm.__bool__, which raises when total is
                # None -> use identity checks instead.
                on_chunk = (lambda n: fbar.update(n)) if fbar is not None else None
                try:
                    nbytes, secs = job.run(self, on_chunk)
                except KeyboardInterrupt:
                    if fbar is not None:
                        fbar.close()
                    dq.appendleft(job)
                    raise
                except Exception as e:  # noqa: BLE001
                    if fbar is not None:
                        fbar.close()
                    job.attempts += 1
                    job.last_error = str(e)
                    say(f"  RETRY[{job.attempts}] {job.label}: {e}")
                    dq.append(job)
                    continue
                if fbar is not None:
                    fbar.close()
                kbs = (nbytes / secs / 1024.0) if secs > 0 else 0.0
                report.record_ok(job, nbytes, secs)
                done += 1
                done_bytes += job.size if job.size is not None else nbytes
                # one fixed-width line that overwrites itself on the target (CR)
                line = progress_line(
                    str(job.dos_path),  # full name+path
                    job.size if job.size is not None else nbytes,
                    done_bytes,
                    total_bytes,
                )
                self._safe_raw(b"\r" + line.encode("ascii", "replace"))
                if overall is not None:
                    overall.update(1)
                say(f"  OK   {job.label}  {nbytes}B {secs:.2f}s {kbs:.1f}KB/s")
        except KeyboardInterrupt:
            say("\n[interrupted] stopping; reporting pending files")
            report.record_pending(list(dq))
        finally:
            if overall is not None:
                overall.close()

    # tree operations ---------------------------------------------------------
    def _plan_upload(self, root: Path, dos_base: str = "") -> list[_Job]:
        """Map a local tree to structure-preserving 8.3 DOS paths (per-directory
        collision sets) and build one upload job per file.  `dos_base` (e.g.
        "UP") nests the whole tree under one DOS directory."""
        root = Path(root)
        taken: dict[str, set] = {}  # dos-parent -> used 8.3 names
        dirmap: dict[Path, str] = {Path(): dos_base}
        for d in sorted(
            (p for p in root.rglob("*") if p.is_dir()),
            key=lambda p: len(p.relative_to(root).parts),
        ):
            rel = d.relative_to(root)
            parent = dirmap[rel.parent]
            name = to_83(d.name, taken.setdefault(parent, set()))
            dirmap[rel] = (parent + "\\" + name) if parent else name
        jobs: list[_Job] = []
        for f in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = f.relative_to(root)
            parent = dirmap[rel.parent]
            name = to_83(f.name, taken.setdefault(parent, set()))
            dos = (parent + "\\" + name) if parent else name
            jobs.append(_Job("up", f, dos, f.stat().st_size))
        return jobs

    def upload_tree(
        self, root: Path, report: TransferReport | None = None, dos_base: str = ""
    ) -> TransferReport:
        report = report or TransferReport()
        self.run_queue(self._plan_upload(root, dos_base), report)
        return report

    def _walk_remote(self, remote_dir: str, local_dir: Path, jobs: list[_Job]) -> None:
        spec = (remote_dir + "\\*.*") if remote_dir else "*.*"
        for name, attr, size in self.list_dir(spec):
            if name in (".", ".."):
                continue
            rpath = (remote_dir + "\\" + name) if remote_dir else name
            if attr & 0x10:  # subdirectory
                self._walk_remote(rpath, local_dir / name, jobs)
            else:
                jobs.append(_Job("down", local_dir / name, rpath, size))

    def download_tree(
        self, remote_dir: str, local_dir: Path, report: TransferReport | None = None
    ) -> TransferReport:
        report = report or TransferReport()
        jobs: list[_Job] = []
        self._walk_remote(remote_dir, Path(local_dir), jobs)
        self.run_queue(jobs, report)
        return report

    def upload_file(
        self, local: Path, dos_path: str, report: TransferReport | None = None
    ) -> TransferReport:
        report = report or TransferReport()
        self.run_queue(
            [_Job("up", local, dos_path, Path(local).stat().st_size)], report
        )
        return report

    def download_file(
        self, remote_path: str, local: Path, report: TransferReport | None = None
    ) -> TransferReport:
        report = report or TransferReport()
        self.run_queue([_Job("down", local, remote_path)], report)
        return report

    def quit(self) -> None:
        with contextlib.suppress(OSError):
            self.xact(T_QUIT)


class SerialTransport:
    """Transport over a real serial port (pyserial), for talking to actual
    vintage hardware.  Matches the .send()/.read_until() API that Link uses."""

    def __init__(self, port: str, baud: int = 9600) -> None:
        import serial  # pyserial; only needed for real hardware

        self.s = serial.Serial(port, baud, timeout=0.1)

    def send(self, data: bytes) -> None:
        self.s.write(data)
        self.s.flush()

    def read_until(self, term: bytes, timeout: float = 5.0) -> bytes:
        end = time.time() + timeout
        out = bytearray()
        while time.time() < end:
            b = self.s.read(1)
            if b:
                out += b
                if out.endswith(term):
                    break
        return bytes(out)


class SocketTransport:
    """Transport over a socket — used to talk to an emulator whose serial port
    is exposed as a Unix socket (QEMU `-serial unix:...,server=on`) or TCP
    (`-serial tcp:...,server,nowait`).  Same .send()/.read_until() API as the
    others."""

    def __init__(self, sock: socket.socket) -> None:
        self.s = sock
        self._timeout_cls = socket.timeout

    @classmethod
    def unix(cls, path: str) -> Self:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(path)
        return cls(s)

    @classmethod
    def tcp(cls, host: str, port: int) -> Self:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        return cls(s)

    def send(self, data: bytes) -> None:
        self.s.sendall(data)

    def read_until(self, term: bytes, timeout: float = 5.0) -> bytes:
        self.s.settimeout(timeout)
        out = bytearray()
        try:
            while not out.endswith(term):
                ch = self.s.recv(1)
                if not ch:
                    break
                out += ch
        except self._timeout_cls:
            pass
        return bytes(out)


def _cli(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="pyc serial file transfer (host side)")
    ap.add_argument("--port", help="real serial device, e.g. /dev/ttyUSB0 or COM3")
    ap.add_argument(
        "--socket", help="emulator serial as a Unix socket, e.g. /tmp/pyc_xfer.sock"
    )
    ap.add_argument("--tcp", help="emulator serial as host:port, e.g. localhost:4555")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--report", help="also write the transfer report to this file")
    ap.add_argument(
        "--selftest", action="store_true", help="run codec self-test and exit"
    )
    sub = ap.add_subparsers(dest="cmd")
    pu = sub.add_parser("upload", help="upload file(s) or directory tree")
    pu.add_argument("paths", nargs="+")
    pd = sub.add_parser("download", help="download a remote file or directory tree")
    pd.add_argument("remote", help="remote 8.3 path; '' or a dir lists & pulls a tree")
    pd.add_argument("local", help="local destination file or directory")
    pd.add_argument(
        "--tree",
        action="store_true",
        help="treat 'remote' as a directory and download it recursively",
    )
    pl = sub.add_parser("dir", help="list files on the target (DOS-style)")
    pl.add_argument(
        "path",
        nargs="?",
        default="",
        help="e.g. A:, C:\\DOS, a *.* spec, or '' for the current dir",
    )
    pl.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="recurse into subdirectories (like dir /s)",
    )
    sub.add_parser("quit", help="tell the agent to exit")
    args = ap.parse_args(argv)

    if args.selftest or not args.cmd:
        _selftest()
        if not args.cmd:
            return 0
    if args.socket:
        transport = SocketTransport.unix(args.socket)
    elif args.tcp:
        host, _, port = args.tcp.rpartition(":")
        transport = SocketTransport.tcp(host, int(port))
    elif args.port:
        transport = SerialTransport(args.port, args.baud)
    else:
        ap.error("one of --port / --socket / --tcp is required")
    link = Link(transport)
    report = TransferReport()
    if args.cmd == "upload":
        taken: set[str] = set()
        for p in args.paths:
            path = Path(p)
            if path.is_dir():
                link.upload_tree(path, report)
            else:
                link.upload_file(path, to_83(path.name, taken), report)
    elif args.cmd == "download":
        if args.tree:
            link.download_tree(args.remote, Path(args.local), report)
        else:
            link.download_file(args.remote, Path(args.local), report)
    elif args.cmd == "dir":
        link.print_dir(args.path, args.recursive)
        return 0
    elif args.cmd == "quit":
        link.quit()
        return 0
    text = report.render()
    print(text)
    if args.report:
        Path(args.report).write_text(text + "\n")
    return 0


def _selftest() -> None:
    # self-test of the pure-Python codec layer (no hardware needed)
    for sample in [b"", b"\x00", b"hello", b"\x00\x00a\x00", bytes(range(256)) * 2]:
        assert cobs_decode(cobs_encode(sample)) == sample, sample
    t: set[str] = set()
    assert to_83("Makefile", t) == "MAKEFILE"
    assert to_83("a_very_long_name.text", t) == "A_VERY~1.TEX"
    assert to_83("a_very_long_other.txt", t) == "A_VERY~1.TXT"  # diff ext -> ~1 ok
    assert to_83("a_very_long_name.text", t) == "A_VERY~2.TEX"  # same -> next ~N
    assert to_83("résumé.DOCX", t) == "R_SUM_.DOC"  # non-ASCII -> '_'
    p = parse_packet(make_frame(T_DATA, 7, b"abc")[:-1])
    assert p == (T_DATA, 7, b"abc"), p
    print("host.py self-test OK")


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
