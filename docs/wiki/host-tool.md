---
title: Host Tool (host.py)
type: code-map
sources:
  - host.py
related:
  - "[[wire-protocol]]"
  - "[[dos-agent]]"
  - "[[mount-fs]]"
  - "[[dos-datetime-format]]"
  - "[[protocol-versioning]]"
  - "[[mountgui]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

## Overview

`host.py` is the Python-side tool that runs on the modern host PC. It speaks the serial transfer protocol over a real RS-232 COM port (pyserial). It also provides the `RemoteFS` callback interface used by `mountfs.py`.

## Top-level imports and constants

```python
T_ACK=0 T_OPEN=1 T_DATA=2 T_CLOSE=3 T_QUIT=4 T_GET=5 T_LIST=7
T_ENTRY=8 T_MSG=9 T_MKDIR=6 T_DEL=10 T_RMD=11 T_REN=12
T_PREAD=13 T_PWRITE=14 T_RAW=15 T_VERSION=16 T_NAK=127
```

CRC tables and COBS codec are inline (no external protocol library).

## Key helpers (module-level)

| Function | Purpose |
|----------|---------|
| `crc16(data)` | CRC-16/CCITT, poly 0x1021, init 0xFFFF |
| `crc32_update(crc, chunk)` | Running CRC-32 for file integrity |
| `cobs_encode(data)` / `cobs_decode(data)` | [[cobs-framing]] |
| `make_frame(type_, seq, data)` | Builds framed packet bytes (COBS + CRC-16) |
| `epoch_to_fat(mtime)` | float mtime → `(fat_date, fat_time)` 16-bit ints |
| `fat_to_epoch(fat_date, fat_time)` | FAT pair → float or `None` if both zero |

`fat_to_epoch` returns `None` when both fields are 0 (meaning "unset") to distinguish from Unix epoch 0.

## `Link` class

The main session object. Constructor takes `port` (str) and `baud` (int), opens pyserial, stores `proto_version = 0`.

### Core communication methods

| Method | Notes |
|--------|-------|
| `read_frame()` | Reads until 0x00 delimiter, COBS-decodes, checks CRC-16 |
| `send(type_, seq, data)` | Calls `make_frame`, writes to serial |
| `xact(type_, data=b"", seq=None)` | Send + wait for matching ACK/NAK; raises `OSError` on bad seq |
| `query_version()` | Sends T_VERSION; empty ACK → `proto_version=0`; ACK+[n] → `proto_version=n`. Returns version int. |

### File transfer methods

| Method | Notes |
|--------|-------|
| `upload_file_once(local, remote)` | Opens file, sends OPEN→DATA chunks→CLOSE. When `proto_version≥1`, appends `fat_time(2 LE) + fat_date(2 LE)` to CLOSE payload. |
| `download_file_once(local, remote)` | Sends GET, receives ENTRY+DATA*+CLOSE. When `proto_version≥1` and `len(close_data)≥8`, parses `time=close_data[4:6]`, `date=close_data[6:8]` and calls `os.utime(local, (mtime, mtime))`. |
| `list_dir(spec)` | Sends LIST, receives ENTRY packets. v0: returns `[(name, attr, size, None)]`; v1: parses time at 5:7, date at 7:9, name from offset 9. |

### Directory / V2 operations

`mkdir`, `delete`, `rmdir`, `rename` — single-packet transactions. `pread(remote, offset, length)` / `pwrite(remote, offset, data)` — partial read/write.

## Job queue and CLI

`_Job` dataclass: `src`, `dst`, `op` ("up"/"dn"/"del"/etc.), `size`, `mtime` (float or None, carries DOS mtime through the queue).

`_walk_remote(spec)` recurses via `list_dir`, yields `_Job` instances. `_plan_upload(local_dir, remote_dir)` collects local files, yields upload `_Job` instances.

`run_queue(jobs)` iterates jobs, calls the appropriate method, prints progress.

### CLI entry point

`main()` parses args (`--port`, `--baud`, subcommands: `put`, `get`, `dir`, `mount`, `rm`, `mkdir`, `rmdir`, `mv`, `raw`). Always calls `link.query_version()` after opening the link.

## Link observer hook

`Link.__init__` accepts an optional `observer: Callable[[str, str], None] | None = None`
parameter (default `None` — zero behaviour change).  When set, `xact` calls it
on every meaningful event:

| Event | When |
|-------|------|
| `"ack"` | ACK with matching seq received — packet succeeded |
| `"nak"` | NAK with matching seq received — will resend |
| `"timeout"` | No frame / bad CRC within timeout — will resend |
| `"fail"` | Retries exhausted — about to raise `OSError` |

`mountgui.LinkStatus.__call__` implements this signature; see [[mountgui]].

## Protocol version flow

```
link = Link(port, baud)
link.query_version()          # → proto_version set
link.upload_file_once(...)    # uses proto_version
link.list_dir(...)            # uses proto_version
```

See [[protocol-versioning]] for the handshake design rationale.

## Timestamp conversion

See [[dos-datetime-format]] for the FAT encoding details. `epoch_to_fat` uses `datetime.fromtimestamp()` in local time (matching how DOS stores timestamps — local, not UTC). `fat_to_epoch` uses `datetime(...).timestamp()` to convert back.
