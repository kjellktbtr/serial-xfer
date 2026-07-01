---
title: "MS-DOS v4.0 Device Drivers"
type: code-map
sources:
  - MS-DOS/v4.0/src/DEV/
related:
  - "[[msdos-v4-architecture]]"
  - "[[msdos-bios-modules]]"
created: 2026-06-26
updated: 2026-06-26
confidence: high
---

# MS-DOS v4.0 Device Drivers

The `DEV/` directory contains device drivers loaded via `DEVICE=` lines in `CONFIG.SYS`. Each driver implements the DOS device driver interface with `STRATEGY` and `INTERRUPT` entry points registered in the device chain.

## Driver Overview

| Directory | Driver | Description |
|-----------|--------|-------------|
| `ANSI/` | ANSI.SYS | ANSI escape sequence processor for terminal control |
| `SMARTDRV/` | SMARTDRV.EXE | Disk cache: buffers disk reads/writes in conventional or upper memory |
| `RAMDRIVE/` | RAMDRIVE.SYS | RAM disk driver: creates virtual disk in conventional/upper memory |
| `VDISK/` | VDISK.SYS | Virtual disk on physical disk file (alternative to RAMDRIVE) |
| `DISPLAY/` | DISPLAY.SYS | Display driver: font loading, code page switching, EGA/LCD support |
| `KEYBOARD/` | KEYBOARD.SYS | Keyboard driver: country-specific layouts (20+ language variants) |
| `PRINTER/` | PRINTER.SYS | Printer driver: font support, parallel port configuration |
| `XMAEM/` | XMAEM.SYS | Extended Memory Manager (IBM XMA card) |
| `XMA2EMS/` | XMA2EMS.SYS | XMA-to-EMS translator: provides EMS interface over XMA hardware |
| `COUNTRY/` | (MKCNTRY) | Country information file generator |
| `DRIVER/` | DRIVER.SYS | Generic device driver framework |

## ANSI.SYS (`DEV/ANSI/`)

Processes ANSI escape sequences for terminal control (cursor movement, screen clearing, text attributes).

| File | Role |
|------|------|
| `ANSI.ASM` | Main driver: strategy/interrupt entry points, command dispatch |
| `ANSI.INC` | Shared equates and macros |
| `ANSIINIT.ASM` | Driver initialization, device chain registration |
| `ANSIVID.INC` | Video mode-specific cursor handling |
| `IOCTL.ASM` | IOCTL handler for driver control |
| `PARSER.ASM` | Escape sequence parser (CSI, OSC, etc.) |

## SMARTDRV (`DEV/SMARTDRV/`)

Disk caching driver. Buffers disk reads and writes, reducing physical disk access. Can operate in conventional memory or upper memory blocks (UMB).

| File | Role |
|------|------|
| `SMARTDRV.ASM` | Main driver: cache management, read/write forwarding |
| `ABOVE.ASM` | Upper memory block (UMB) allocation support |
| `AB_MACRO.ASM` | Above-1MB memory macros |
| `CMACROS.INC` | Common macros for cache operations |
| `DEVSYM.ASM` | Device symbol definitions |
| `DIRENT.ASM` | Directory entry handling for cache invalidation |
| `EMM.ASM` | EMM (Expanded Memory Manager) interface for UMB allocation |
| `FL13.ASM` | INT 13h hook: intercepts BIOS disk calls for caching |
| `FLMES.ASM` | Message strings |
| `FLUSH13.C` | INT 13h flush utility |
| `INT13.DOC` | INT 13h hook documentation |
| `LOADALL.ASM` | Real-mode to protected-mode transition for cache above 1MB |
| `MI.ASM` | Memory interface routines |
| `SYSCALL.ASM` | DOS syscall wrappers |

## RAMDRIVE (`DEV/RAMDRIVE/`)

Creates a virtual disk in RAM. Supports FAT12 file system. Can be placed in conventional or upper memory.

| File | Role |
|------|------|
| `RAMDRIVE.ASM` | Main driver: disk I/O strategy/interrupt, FAT management |
| `ABOVE.INC` | Upper memory support |
| `AB_MACRO.INC` | Above-1MB macros |
| `DEVSYM.INC` | Device symbols |
| `DIRENT.INC` | Directory entry structures |
| `EMM.INC` | EMM interface for UMB allocation |
| `LOADALL.INC` | Protected mode transition |
| `MESSAGES.ASM` | Error messages |
| `MI.INC` | Memory interface |
| `SYSCALL.INC` | DOS syscall wrappers |

## VDISK (`DEV/VDISK/`)

Virtual disk stored as a file on physical disk (vs. RAM-only like RAMDRIVE).

| File | Role |
|------|------|
| `VDISK.ASM` | Main driver: file-backed virtual disk I/O |
| `VDISK.INC` | Shared definitions |
| `VDISKMSG.ASM` | Messages |
| `VDISKSYS.ASM`, `VDISKSYS.INC` | System integration routines |

## DISPLAY.SYS (`DEV/DISPLAY/`)

Display driver for font management and code page switching. Supports EGA and LCD displays.

| File | Role |
|------|------|
| `DISPLAY.ASM` | Main driver: font loading, display initialization |
| `DISPMES.ASM` | Messages |
| `INIT.ASM` | Driver initialization |
| `PARSER.ASM` | Parameter parsing |
| `INT10COM.INC` | INT 10h (video) common routines |
| `INT2FCOM.INC` | INT 2Fh common routines |
| `MACROS.INC` | Shared macros |
| `TABLES.INC` | Display mode tables |
| `WRITE.INC` | Write operations |
| `CPS-FUNC.INC` | Code page services |
| `DEF-EQU.INC` | Default equates |
| `F-PARSER.INC` | Format parser |

### Font Directories

- `EGA/` — EGA font files (8×8, 8×14, 8×16) for code pages 437, 850, 860, 863, 865
- `LCD/` — LCD font files for code pages 437, 850, 860, 863, 865

## KEYBOARD.SYS (`DEV/KEYBOARD/`)

Keyboard driver with 20+ country-specific layout files.

| File | Role |
|------|------|
| `KDF.ASM` | Main keyboard driver |
| `KEYBMAC.INC` | Keyboard macros |
| `KEYBSHAR.INC` | Shared keyboard routines |
| `KDFxx.ASM` | Country-specific layouts: BE, CF, DK, EOF, FR, FR120, FR189, GE, IT, IT141, IT142, LA, NL, NO, NOW, PO, SF, SG, SP, SU, SV, UK, UK166, UK168 |

## PRINTER.SYS (`DEV/PRINTER/`)

Printer driver with font support and parallel port configuration.

| File | Role |
|------|------|
| `PARSER.ASM`, `PARSE4E.ASM` | Parameter parsing |
| `PRTINT2F.ASM` | INT 2Fh handler |
| `PTRMSG.ASM` | Messages |
| `CPSPI*.ASM` | Code page services for printer |
| `CPSFONT.ASM`, `CPSFONT3.ASM` | Font handling |
| `CPSPEQU.INC` | Printer equates |
| `4201/`, `4208/`, `5202/` | Printer-specific font files (Daisy Wheel, etc.) |

## XMAEM / XMA2EMS (Extended Memory)

| Directory | Driver | Role |
|-----------|--------|------|
| `XMAEM/` | XMAEM.SYS | IBM XMA Extended Memory Manager — manages XMA hardware directly |
| `XMA2EMS/` | XMA2EMS.SYS | Translates XMA hardware to EMS (Expanded Memory Specification) API |

Key files in XMAEM:
- `INDEINI.ASM` — Initialization
- `INDEEMU.ASM` — Memory emulation
- `INDEGDT.ASM`, `INDEIDT.ASM` — GDT/IDT setup (protected mode)
- `INDEI15.ASM` — INT 15h handler
- `INDEXMA.ASM` — Main XMA interface

Key files in XMA2EMS:
- `XMA2EMS.ASM` — Main EMS translator
- `EMSINIT.INC` — EMS initialization
- `I13HOOK.INC` — INT 13h hook for EMS paging
- `ROMSCAN.INC` — ROM detection

## Device Driver Interface

All drivers follow the DOS device driver chain protocol:

1. **Header**: 5-byte signature (`DU` or `DR`), flags word, STRATEGY and INTERRUPT far pointers
2. **STRATEGY**: Queues I/O request block (IORB), returns immediately
3. **INTERRUPT**: Processes queued requests, returns status via IORB
4. **Chain**: Each driver's header contains pointer to next driver (or NULL for end of chain)

Driver attributes (from `DEVSYM.INC`):
- `DEV_ATTRIB_CON` (01h) — Console device
- `DEV_ATTRIB_BLOCK` (04h) — Block device (disk)
- `DEV_ATTRIB_CHAR` (08h) — Character device
- `DEV_ATTRIB_EXCL` (10h) — Exclusive access
- `DEV_ATTRIB_IOCTL` (80h) — Supports IOCTL
