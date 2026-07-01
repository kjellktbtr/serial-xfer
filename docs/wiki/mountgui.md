---
title: Mount GUI (mountgui.py)
type: code-map
sources:
  - mountgui.py
  - mountfs.py
  - host.py
related:
  - "[[mount-fs]]"
  - "[[host-tool]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

## Overview

`mountgui.py` provides a Tkinter control panel for mounting a DOS filesystem
over a serial link.  It is launched automatically when `mountfs.py` is invoked
with no command-line arguments:

```python
# mountfs.py  main()
if not argv:
    import mountgui
    mountgui.build_and_run()
    return 0
```

The module has **no top-level Tk import** so it can be imported and tested
headlessly (e.g. `test_com.py::test_link_status_observer`).

## Components

### `LinkStatus`

Thread-safe shared state — the hub between the mount worker thread and the GUI
poll loop.

```python
class LinkStatus:
    state: str     # "idle" | "ok" | "nak" | "no_reply" | "error"
    message: str
    _samples: deque[tuple[float, int]]  # (monotonic_time, nbytes)
```

**As a `Link` observer** (`host.Link(transport, observer=status)`):

| `event` arg | resulting `state` |
|-------------|-------------------|
| `"ack"` | `"ok"` |
| `"nak"` | `"nak"` |
| `"timeout"` | `"no_reply"` |
| `"fail"` | `"error"` |

**Direct setters** used by the mount thread:
- `set_ok(msg)` — e.g. `"Connected"`, `"Crawling root…"`, `"Mounted"`.
- `set_error(msg)` — exception message; displayed in red.

**Speed**: `add_bytes(n)` records a sample; `speed_bps()` / `snapshot()` return
the bytes/sec over a 2-second rolling window.

### `_MonitoredTransport`

Wraps any `Transport` and calls `status.add_bytes(len(data))` on both `send()`
and `read_until()` so the speed readout covers all wire traffic (crawl, reads,
writes).

### Platform helpers

| Function | Notes |
|----------|-------|
| `list_serial_ports()` | `serial.tools.list_ports.comports()` device names; empty list if pyserial missing |
| `free_drive_letters()` | Windows: letters D–Z not in use (`GetLogicalDrives` bitmask) |
| `unmount(mountpoint)` | POSIX: `fusermount -u`, then `umount`. Windows: no-op (use WinFsp tray or `net use X: /delete`) |

### `build_and_run()`

Builds the window and runs the Tk event loop; blocks until the window is
destroyed.

**GUI layout** (top to bottom):
1. **Serial port** — editable `Combobox` auto-populated from `list_serial_ports()` + Refresh button `⟳`.
2. **Baud rate** — editable `Combobox`, values 2400/4800/9600/19200/38400/57600/115200, default 9600.
3. **Remote root** — plain `Entry`, default `C:\`.
4. **Mount at** — Linux/macOS: path `Entry` + Browse button; Windows: drive-letter `Combobox`.
5. **Status label** — colored; green=ok, amber=nak/no_reply, red=error.  Speed appended when > 50 B/s.
6. **Mount / Unmount** (toggle) + **Close** buttons.

**Mount flow** (worker thread):
1. `SerialTransport(port, baud)` wrapped in `_MonitoredTransport`.
2. `Link(monitored, observer=status)` → `query_version()`.
3. `RemoteFS(link, dos_root)` → `rfs.start()` (BFS crawl of root dir as connectivity probe).
4. `FUSE(_build_fuse_ops(rfs), mountpoint, foreground=True, nothreads=False)` — blocks until unmount.  FUSE's `destroy()` calls `link.quit()`.
5. On any exception: `status.set_error(str(e))`.

**GUI thread** polls `status.snapshot()` via `root.after(200, _poll)`.  When the
worker thread ends, `_poll` re-enables all inputs and resets the Mount button.

**Unmount / Close** both call `unmount(mountpoint)` (POSIX) and wait for the
thread to finish via the polling loop.  A `_closing` flag tells `_poll` to call
`root.destroy()` once the thread exits.

## Threading model

- All Tk widget mutations happen on the main thread via `_poll`.
- The worker thread communicates only through `LinkStatus` (lock-protected) and
  the `threading.Thread.is_alive()` check.
- `root.after(0, callback)` is not used here; the 200 ms polling interval is
  sufficient latency for the status updates.

## Windows limitations (untested)

- `unmount()` is a no-op; the user must unmount via the WinFsp system-tray icon
  or `net use X: /delete`.  As a result the "Unmount" button in the GUI does
  nothing on Windows.  Tracked in `docs/improvements.md`.
- Drive-letter `Combobox` is populated with `free_drive_letters()` but is fully
  editable.
