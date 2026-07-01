# serial-xfer project changelog

Append a dated entry per feature/fix.  Format: `## YYYY-MM-DD HH:MM — <summary>`

---

## 2026-07-01 12:00 — Initial project commit

Implemented XFER.COM (hand-written NASM 8086 DOS agent, ~2.4 KB), host.py
(upload/download/dir/mount tools), mountfs.py (FUSE filesystem), test_com.py
(emulator-free regression suite using Unicorn), PROTOCOL.md (wire spec),
dosbox-xfer.conf + run_dosbox.sh (DOSBox test path).

## 2026-07-01 12:30 — CLI args for baud rate and COM port

Added `parse_args` to `xfercom.asm`: `XFER [baud [com]]` syntax lets you select
baud rate and COM port (1–4) at runtime without recompiling.  Updated README.md
with the baud-rate table and tested values on the IBM 5155.

## 2026-07-01 — Tkinter GUI for mountfs.py

Running `python mountfs.py` with no arguments now opens a small control panel
instead of printing a usage error.  New `mountgui.py` provides:
- Editable comboboxes for serial port (auto-detected from pyserial), baud rate
  (2400–115200 with a custom entry option), remote root (default `C:\`), and
  mount target (directory picker on Linux/macOS; drive-letter combobox on Windows).
- Mount / Unmount button (toggle) and Close button; graceful unmount on close.
- Color-coded status label (green = OK, amber = NAK/no-reply retrying, red = error)
  with live transfer speed (KB/s) derived from a rolling 2-second byte-rate window.
- `host.Link` gained an optional `observer(event, message)` callback (4 new event
  emits in `xact`: `"ack"`, `"nak"`, `"timeout"`, `"fail"`); default `None` is
  a no-op so existing CLI behaviour and all tests are unaffected.
- New headless test `test_link_status_observer` in `test_com.py` covers the
  state-machine, byte-rate, NAK→ACK and timeout→fail paths without hardware.

## 2026-07-01 — Protocol versioning + file timestamps + Windows mount + wiki/process bootstrap

**Protocol versioning (T_VERSION=16):** Host sends T_VERSION once at session start;
a v1 agent replies ACK+[0x01]; a v0 agent returns empty ACK.  All v1 extensions
are gated on the negotiated version, keeping old agents fully compatible.

**File date/time preservation (v1):**
- `xfercom.asm`: added `do_getftime`/`do_setftime` helpers (INT 21h AH=57h);
  `serve_list` now includes packed FAT time+date in ENTRY packets (between size
  and name); `serve_get` reads file date/time before closing and appends it to
  the CLOSE payload; `.h_close` reads date/time from the host's v1 CLOSE and
  calls `do_setftime` on the open handle.  XFER.COM grows from ~2489 to 2636 bytes.
- `host.py`: added `T_VERSION`, `epoch_to_fat`, `fat_to_epoch`,
  `Link.query_version()`, `Link.proto_version`; updated `upload_file_once`
  (appends FAT date/time to CLOSE payload when v1), `download_file_once` (parses
  date/time from CLOSE and applies via `os.utime`), `list_dir` (returns 4-tuple
  with mtime), `_dir_one`, `_walk_remote`, `_Job` (mtime field).
- `mountfs.py`: `Node` gains `mtime` slot; `_ensure_listed` stores mtime from
  directory listings; `_attr` uses `node.mtime` so `ls -l` shows real DOS dates.

**Windows mount support (WinFsp):**
- `mountfs.py` now tries `fuse` (fusepy/libfuse) first, then falls back to
  `winfsp.fuse` (WinFsp's fusepy-compatible binding) when not on Linux.
  `os.getuid()`/`os.getgid()` guarded with `hasattr` for Windows compat.
  `st_uid`, `st_gid`, `st_nlink`, `st_mode` remain but are cosmetic under WinFsp.
- README.md: added Windows/WinFsp section.  Needs testing on a real Windows machine.

**Test suite fixes and additions:**
- Fixed two pre-existing regressions introduced by the CLI arg-parsing commit:
  `test_framing` now pre-seeds `v_base=0x3F8` (since `send_packet`/`read_frame`
  are called without running `parse_args`); `_boot()` now writes a proper PSP
  command tail (0x0D at 0x81) so `parse_args` sees no args and uses defaults.
- `_boot()` calls `link.query_version()` so all tests run with the correct
  `proto_version` set.
- Added `test_version_and_timestamps()`: verifies version=1, ENTRY date/time
  parsing, download mtime via `os.utime`, and upload `do_setftime`.
- Updated `test_size` limit from 2200 → 2800 (CLI args + timestamp additions).

**Docs + process bootstrap:**
- Updated `PROTOCOL.md`: added versioning section, T_VERSION packet, v1 ENTRY/CLOSE
  layouts, FAT date/time format note.
- Seeded `docs/wiki/` with index, log, and initial wiki pages.
- Updated root `CLAUDE.md` with project overview, key files, and standing
  per-session workflow (improvements checklist, changelog, wiki).
- Updated `docs/improvements.md`: ticked off timestamps and Windows mount;
  added new follow-up items.

## 2026-07-01 — Ingest docs/raw/1/ into the wiki: 16-bit real-mode reference (DOS + bare-metal)

Ingested the reference corpus in `docs/raw/1/` (OSDev/Wikipedia articles, the
clean 8086 instruction-set HTML reference, the full NASM manual, the Sybex
"Programming the 8086/8088" book, and Ralf Brown's Interrupt List) into
`docs/wiki/`, so the project has on-hand documentation for both DOS-based and
bare-metal 16-bit real-mode assembly programming.

- New concept/reference pages: `x86-16bit-cpu.md`, `8086-instruction-set.md`,
  `bare-metal-boot.md`, `bios-services.md`, `dos-int21-api.md`,
  `debugging-dos-programs.md`. Each is cross-referenced against `xfercom.asm`'s
  actual usage (e.g. `8086-instruction-set.md` documents the exact
  80186+-only instructions `cpu 8086` forbids; `bios-services.md` notes that
  `xfercom.asm` bypasses INT 14h in favor of direct 8250 UART port I/O).
- New source-summary index pages under `docs/wiki/sources/` for the three
  references too large to inline: `nasm-manual.md`, `ralf-brown-interrupt-list.md`,
  `programming-8086-8088.md` (flags the source book's OCR quality issue).
- Fixed the pre-existing orphaned `x86-real-mode.md`: corrected stale
  `sources:` paths, repaired dangling `[[sources/nasmdoc]]` /
  `[[sources/bios-and-boot]]` / `[[sources/msdos-int21]]` links, removed
  references to a different project's pyc/OpenWatcom toolchain, and added it
  to `docs/wiki/index.md` (it was never indexed).
- Flagged (not fixed) two pre-existing dangling references in the older
  `msdos-*.md` pages from a prior project incarnation — see `docs/improvements.md`.
