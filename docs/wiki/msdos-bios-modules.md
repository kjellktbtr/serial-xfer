---
title: "MS-DOS v4.0 BIOS Modules"
type: code-map
sources:
  - MS-DOS/v4.0/src/BIOS/*.ASM
related:
  - "[[msdos-v4-architecture]]"
  - "[[sources/bios-and-boot]]"
created: 2025-06-26
updated: 2025-06-26
confidence: high
---

# MS-DOS v4.0 BIOS Modules

The BIOS layer (`BIOS/`) provides hardware abstraction for MS-DOS. It is linked into `IBMBIO.COM` and loaded during boot. The link order is defined in `MSBIO1.ASM`:

```
msbio1 + msSTACK + MsCON + msAUX + msLPT + msCLOCK + msdISK + msBIO2 + disk + msinit + sysinit1 + sysinit2 + sysimes
```

## Core BIOS Modules

| File | Description |
|------|-------------|
| `MSBIO1.ASM` | **Main BIOS entry point.** Contains link configuration, core BIOS routines, device driver infrastructure (strategy/complete handlers), and device initialization for CON, AUX, LPT, CLOCK, and DISK. Defines the `BREAK` macro and `POPFF` macro for interrupt handling. |
| `MSBIO2.ASM` | **Second BIOS module.** Handles disk operations, error recovery, INT 2Fh extensions, and the INT 13h disk hook chain. Contains `SWPDSK` (disk swap) and `INT2F_DISK` handlers. |

## Device Drivers

| File | Description |
|------|-------------|
| `MSCON.ASM` | **Console device driver.** Handles keyboard input (`CON$READ`) and screen output (`CON$WRIT`). Supports multiple video modes (monochrome, color, ANSI). Implements the CON device for DOS device I/O. |
| `MSAUX.ASM` | **Auxiliary (serial) device driver.** RS-232 port support for AUX, COM1, COM2. Implements read, write, flush, and status operations. Configurable baud rate and port settings. |
| `MSLPT.ASM` | **Parallel printer driver.** LPT1/LPT2 support with timeout and retry logic. Handles printer busy/error status polling. |
| `MSCLOCK.ASM` | **Clock device driver.** Sets and reads system time from CMOS RTC. Converts time to clock ticks (~18.2/sec). Provides INT 08h timer interrupt handler. |

## Disk I/O

| File | Description |
|------|-------------|
| `MSDISK.ASM` | **Disk BIOS driver.** Manages floppy and hard disk I/O via INT 13h. Handles media checking, disk base tables (BDS), ECC error recovery, and DASD ERP (Error Recovery Procedure). Supports multi-density floppies, 96 TPI media, and hard disk partition tables. Key revision history tracks fixes for unformatted media access, ECC errors, and diskcopy compatibility. |
| `MSHARD.ASM` | **Hard disk INT 13h interceptor.** Patches IBM AT ROM BIOS bug where interrupts are not disabled during hard disk reads. Ensures data integrity by wrapping INT 13h calls with CLI/STI. |

## Initialization

| File | Description |
|------|-------------|
| `MSINIT.ASM` | **BIOS initialization.** Boot record processing, motor start time configuration, CMOS clock setup, and day-to-date conversion (`Daycnt_to_day`, `Bin_to_bcd`). Handles INT 6C resume. Key revisions: boot from systems with no floppy drives, 386 double-word MOV, FAT table extension to 64K entries, OS/2 boot record support, extended keyboard recognition. |
| `MSLOAD.ASM` | **Non-contiguous IBMBIO loader.** Loads `IBMBIO.COM` in pieces to handle large BIOS images. Supports 32-bit address calculation and FAT sector reading during boot. |
| `SYSINIT1.ASM` | **System initialization (part 1).** Memory management setup, EMS (Expanded Memory Specification) detection, SHARE installation, and device driver chain initialization. |
| `SYSINIT2.ASM` | **System initialization (part 2).** CONFIG.SYS processing, DBCS (Double-Byte Character Set) support, hardware stack switching, and final boot completion. |

## Configuration

| File | Description |
|------|-------------|
| `SYSCONF.ASM` | **CONFIG.SYS parser.** Processes configuration directives: `DEVICE=`, `INSTALL=`, `BUFFERS=`, `STACKS=`, `FILES=`, `SHELL=`, `BREAK=`, `INSTALLSWITCH=`, `DOS=HIGH`, `DOS=UMB`, `FCBS=`, `LASTDRIVE=`, `COUNTRY=`. Parses command-line switches and environment variables. |
| `SYSIMES.ASM` | **System initialization messages.** Contains boot-time error strings: `BADMEM` (bad memory configuration), `BADSTACK` (bad stack settings), `BADCOM` (bad COM settings), `BADBREAK`, `BADFCB`, `BADLASTDRIVE`, `BADFCBS`, `BADDOS`, `BADINSTALL`, `BADDEVICE`, `BADPATH`, `BADFCB`, `BADFCBS`, `BADFCB`, `BADFCBS`. |

## BIOS Data Structures

Key data structures referenced across BIOS modules:

| Structure | Location | Purpose |
|-----------|----------|---------|
| **BDS** (Disk Base Table) | `MSDISK.ASM` | Per-drive disk parameters: media type, sectors/track, heads, starting track, BPB pointer |
| **DPB** (Drive Parameter Block) | Built from BPB | Runtime drive info: sector size, cluster mask/shift, FAT start/count, root entries |
| **Device Header** | `MSBIO1.ASM` | Linked list of device drivers: attributes, strategy/complete pointers, device name |
| **PDB** (Process Data Block) | `SYSINIT1.ASM` | Per-process environment: current directory, default drive, FCB pointers |

## BIOS Interrupt Vectors

The BIOS installs these interrupt vectors during initialization:

| Interrupt | Function |
|-----------|----------|
| INT 08h | Timer tick (18.2 Hz) |
| INT 0Ch | Resume handler (used by INT 24 error handler) |
| INT 13h | Disk services (read/write/verify/format/status/reset) |
| INT 16h | Keyboard services |
| INT 1Ch | Timer tick handler (user hookable) |
| INT 24h | Hard error handler |
| INT 25h | Unconditional overlay load |
| INT 26h | Unconditional overlay move |
| INT 2Fh | Multiplex interrupt (extensions) |

## Revision History Highlights

From `MSDISK.ASM` and `MSINIT.ASM` headers:

- **AN001**: Multi-track enable/disable in CONFIG.SYS
- **AN003**: DASD ERP updated per Storage Systems recommendation
- **AN004-AN006**: Unformatted media access toggle (IOCTL subfunction 64h/44h)
- **AN010**: ECC error handler covers PC ATs for CMC disks
- **AN002**: Boot from systems with no floppy drives
- **AN004**: FAT tables extended to 64K entries (D64)
- **AN007**: OS/2 boot record support
- **AN013**: Extended keyboard recognition
