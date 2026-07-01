# Wiki Operation Log

Append-only.  One line per operation.  Format: `YYYY-MM-DD — <verb> <page>: <brief note>`

---

2026-07-01 — bootstrap wiki: created index.md and log.md
2026-07-01 — create dos-agent.md: xfercom.asm code map (entry point, dispatch, BSS, UART, INT 21h helpers, CLI parsing, test notes)
2026-07-01 — create host-tool.md: host.py code map (Link class, FAT helpers, job queue, CLI)
2026-07-01 — create mount-fs.md: mountfs.py code map (Node, RemoteFS, DosFuse, WinFsp compat, utimens limitation)
2026-07-01 — create wire-protocol.md: full packet type table, ENTRY/CLOSE v0/v1 layouts, framing and CRC notes
2026-07-01 — create cobs-framing.md: COBS concept, encoding/decoding algorithm, why chosen over alternatives
2026-07-01 — create crc-checks.md: CRC-16/CCITT per-packet + CRC-32 whole-file, rationale, implementation notes
2026-07-01 — create dos-datetime-format.md: FAT packed date/time bit layout, INT 21h AH=57h, DTA offsets, Python helpers
2026-07-01 — create protocol-versioning.md: T_VERSION handshake decision — why type 16, backward compat guarantee, version gate table
2026-07-01 — create mountgui.md: Tkinter GUI code-map (LinkStatus, _MonitoredTransport, build_and_run, threading model, Windows limitations)
2026-07-01 — update host-tool.md: added Link observer hook section (event table, mountgui link)
2026-07-01 — update mount-fs.md: noted no-arg GUI launch in main() section
2026-07-01 — ingest docs/raw/1/: create x86-16bit-cpu.md (registers, flags, 8086 vs 8088, addressing modes, I/O ports)
2026-07-01 — ingest docs/raw/1/: create 8086-instruction-set.md (instruction categories + cpu 8086 forbidden-instruction list)
2026-07-01 — ingest docs/raw/1/: create bare-metal-boot.md (BIOS boot sequence, bootsector contract, IVT hooking, no-DOS)
2026-07-01 — ingest docs/raw/1/: create bios-services.md (INT 10h/13h/14h/15h/16h/17h/1Ah tables; notes xfercom.asm bypasses INT 14h)
2026-07-01 — ingest docs/raw/1/: create dos-int21-api.md (INT 21h grouped by category, cross-refed to xfercom.asm's do_* helpers)
2026-07-01 — ingest docs/raw/1/: create debugging-dos-programs.md (qemu/bochs/gdb recipes; flags stale tool paths from source doc)
2026-07-01 — ingest docs/raw/1/: create sources/nasm-manual.md (BITS/CPU directives, .COM production, local labels, EQU/TIMES)
2026-07-01 — ingest docs/raw/1/: create sources/ralf-brown-interrupt-list.md (RBIL file map, entry format, category letters, grep recipes)
2026-07-01 — ingest docs/raw/1/: create sources/programming-8086-8088.md (Sybex book chapter map, OCR quality caveat)
2026-07-01 — ingest docs/raw/1/: create sources/osdev-articles.md (traceability index for 5 absorbed OSDev/Wikipedia articles)
2026-07-01 — update x86-real-mode.md: fixed stale sources: (docs/raw/1/ paths), repaired dangling [[sources/nasmdoc]]/[[sources/bios-and-boot]]/[[sources/msdos-int21]] links, removed pyc/OpenWatcom references (not applicable to this project), added to index.md (was orphaned)
