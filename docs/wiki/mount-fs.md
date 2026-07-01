---
title: Mount Filesystem (mountfs.py)
type: code-map
sources:
  - mountfs.py
related:
  - "[[host-tool]]"
  - "[[wire-protocol]]"
  - "[[dos-datetime-format]]"
  - "[[mountgui]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

## Overview

`mountfs.py` exposes a DOS filesystem over FUSE (Linux/macOS) or WinFsp (Windows). The DOS side looks like a normal directory tree; the modern side is a mountpoint where files can be read, written, moved, and deleted as if they were local.

## Components

### `Node`

A lightweight cached directory entry:
```python
@dataclass(slots=True)
class Node:
    name: str
    is_dir: bool
    size: int
    attr: int       # DOS attribute byte (0x10 = directory)
    mtime: float | None  # Unix epoch from DOS FAT date+time, or None
    children: dict | None = None   # populated by _ensure_listed
```

`mtime` is `None` when: (a) talking to a v0 agent (no timestamp support), or (b) DOS recorded date+time = 0.

### `RemoteFS`

Portable core — no FUSE dependency. Manages the cache of `Node` objects and delegates all wire operations to a `Link`.

| Method | Notes |
|--------|-------|
| `_ensure_listed(path)` | Calls `link.list_dir(path+"\\*")`, populates `children`. v1: stores `mtime` from each `_Job`/entry. |
| `_node(path)` | Resolves a path string to a `Node`, listing parents as needed. |
| `getattr(path)` | Returns `(size, is_dir, mtime)` |
| `readdir(path)` | Returns list of names |
| `read(path, offset, length)` | Uses `link.pread` |
| `write(path, offset, data)` | Uses `link.pwrite`; creates file first if needed |
| `mkdir(path)` | Uses `link.mkdir` |
| `rename(src, dst)` | Uses `link.rename` |
| `unlink(path)` | Uses `link.delete` |
| `rmdir(path)` | Uses `link.rmdir` |

### `DosFuse` / FUSE binding

`_build_fuse_ops()` creates a FUSE operations object that wraps `RemoteFS`. Uses late-binding FUSE import so it can fall back to WinFsp:

```python
try:
    from fuse import FUSE, Operations, FuseOSError
except ImportError:
    from winfsp.fuse import FUSE, Operations, FuseOSError
```

**Platform guard for UID/GID:** `os.getuid()`/`os.getgid()` are POSIX-only. Uses `uid = os.getuid() if hasattr(os, "getuid") else 0` to avoid `AttributeError` on Windows.

#### `_attr(node)` — stat fields

```python
now = time.time()
t = node.mtime if node.mtime is not None else now
return {
    "st_mode": (0o40755 if node.is_dir else 0o100644),
    "st_size": node.size,
    "st_mtime": t,
    "st_atime": t,
    "st_ctime": t,
    "st_nlink": 2 if node.is_dir else 1,
    "st_uid": uid,
    "st_gid": gid,
}
```

When `node.mtime is None` (v0 agent or DOS time unset), the stat times fall back to `now`. This means `ls -l` shows real DOS dates when talking to a v1 agent and "now" otherwise.

### `utimens` — current limitation

`utimens` (the FUSE call to set file times) is a **no-op**. Files written through the mount will have their mtime reported as the current time rather than the write time. Setting the DOS date on a mounted-written file would require a set-by-name packet — there is none today. Tracked in [[improvements]].

## WinFsp (Windows) support

Install prerequisites:
1. [WinFsp](https://winfsp.dev) (FUSE for Windows kernel driver)
2. `pip install winfsp` (Python binding)

Usage: same CLI as Linux — `python mountfs.py <port> <baud> <mountpoint>`.

The `st_uid`, `st_gid`, `st_nlink`, `st_mode` fields are accepted but ignored by WinFsp; Windows permissions work differently. The FUSE operations (read/write/mkdir/rename/unlink) function identically.

**Untested on a real Windows machine as of 2026-07-01.** See `docs/improvements.md`.

## `main()`

When called with **no arguments** (`python mountfs.py`), `main()` immediately
delegates to `mountgui.build_and_run()` and returns — the Tkinter control panel
handles everything from there (see [[mountgui]]).

When called with arguments the existing argparse path runs unchanged:
```python
link = Link(port, baud)
link.query_version()    # determines proto_version for timestamp support
rfs = RemoteFS(link)
rfs.start(mountpoint)
```

Calling `query_version()` before `rfs.start()` ensures mtime data flows from the first directory listing.

## Testing

`test_com.py::test_mount` exercises RemoteFS crawl + getattr/readdir/read/write/mkdir/rename/unlink via the Unicorn emulator backend. FUSE ops are not tested (would need a FUSE mount in CI); only the `RemoteFS` layer is covered.
