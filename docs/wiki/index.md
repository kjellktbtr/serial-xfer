# serial-xfer Wiki — Master Catalog

LLM-generated and maintained knowledge base for the serial-xfer project.
Update this file whenever a wiki page is created or significantly changed.

## Pages

### Code maps
- [dos-agent.md](dos-agent.md) — `xfercom.asm` / `XFER.COM`: architecture, entry point, dispatch, key routines, BSS layout, cpu 8086 constraints
- [host-tool.md](host-tool.md) — `host.py`: Link class, framing helpers, transfer jobs, CLI
- [mount-fs.md](mount-fs.md) — `mountfs.py`: RemoteFS cache, FUSE binding, WinFsp compat

### Source summaries
- [wire-protocol.md](wire-protocol.md) — Summary of `PROTOCOL.md`: all packet types, layouts, versioning, notable details
- [sources/nasm-manual.md](sources/nasm-manual.md) — Indexed NASM manual: BITS/CPU directives, `.COM` file production, local labels, EQU/TIMES
- [sources/ralf-brown-interrupt-list.md](sources/ralf-brown-interrupt-list.md) — RBIL index: file map, entry format, category letters, how to grep it
- [sources/programming-8086-8088.md](sources/programming-8086-8088.md) — Sybex 1983 book chapter map (⚠️ OCR quality caveat)
- [sources/osdev-articles.md](sources/osdev-articles.md) — Traceability index for the 5 short OSDev/Wikipedia raw articles

### Concepts
- [cobs-framing.md](cobs-framing.md) — COBS framing: why, how it works, byte layout
- [crc-checks.md](crc-checks.md) — CRC-16/CCITT per-packet + CRC-32 whole-file
- [dos-datetime-format.md](dos-datetime-format.md) — FAT/DOS packed date+time format, Python helpers
- [x86-16bit-cpu.md](x86-16bit-cpu.md) — 8086/8088 registers, FLAGS bit layout, 8086-vs-8088 bus width, addressing modes, I/O ports
- [8086-instruction-set.md](8086-instruction-set.md) — Instruction set by category, with the `cpu 8086` forbidden-instruction list (PUSHA/POPA/PUSH imm/imm-count shifts)
- [x86-real-mode.md](x86-real-mode.md) — 16-bit real-mode programming guide: memory model, COM/EXE layout, calling conventions, BIOS/DOS snippets
- [bare-metal-boot.md](bare-metal-boot.md) — Programming without DOS: BIOS boot sequence, boot-sector contract, IVT hooking
- [bios-services.md](bios-services.md) — BIOS interrupt services (INT 10h/13h/14h/15h/16h/17h/1Ah), why this project bypasses INT 14h
- [dos-int21-api.md](dos-int21-api.md) — DOS INT 21h API grouped by category, cross-referenced to `xfercom.asm`'s actual calls
- [debugging-dos-programs.md](debugging-dos-programs.md) — Debugging a DOS binary under qemu/bochs/DOSBox (⚠️ source paths are from a different project)

### Decisions
- [protocol-versioning.md](protocol-versioning.md) — Why T_VERSION=16 handshake instead of a hard protocol break; design rationale

### GUI
- [mountgui.md](mountgui.md) — `mountgui.py`: Tkinter mount control panel (LinkStatus, _MonitoredTransport, platform helpers, build_and_run)
