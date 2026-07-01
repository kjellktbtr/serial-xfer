---
title: BIOS Interrupt Services (INT 10h/13h/14h/15h/16h/17h/1Ah)
type: reference
sources:
  - docs/raw/1/bios.txt
  - docs/raw/1/bios2.txt
  - docs/raw/1/ralf_brown_interrupts/dos_int_ref.md
  - docs/raw/1/ralf_brown_interrupts/ (INTERRUP.A, INTERRUP.B — full detail; grep as needed)
related:
  - "[[bare-metal-boot]]"
  - "[[dos-int21-api]]"
  - "[[dos-agent]]"
  - "[[sources/ralf-brown-interrupt-list]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

BIOS services are the low-level API available in real mode with or without
DOS: set `AH` (sometimes `AX`/`EAX`), issue the matching `INT`, read results
from registers. On error, BIOS functions almost always set the **carry flag**
— test with `jc` after every call. [bios.txt:11-22, 262-269]

## Calling convention

```nasm
mov ah, 0x0E        ; select function via AH (+ interrupt number)
mov al, 'X'         ; other registers = arguments
mov bh, 0
int 0x10            ; invoke
jc  .error          ; CF set = error (nearly universal convention)
```

BIOS promises to preserve every register not documented as a return value.
Historical caveat: pre-2.3 Bochs trashed the upper 16 bits of 32-bit
registers even when the 16-bit half was correctly preserved — a reminder to
test on real/accurate hardware when in doubt. [bios.txt:255-269]

## INT 10h — Video

| AH/AX | Function |
|---|---|
| 00h | Set video mode (AL = mode, see table below) |
| 01h | Set cursor shape (CH=start line, CL=end line) |
| 02h | Set cursor position (BH=page, DH=row, DL=col) |
| 03h | Get cursor position |
| 05h | Select active display page |
| 06h/07h | Scroll window up/down |
| 08h | Read char+attribute at cursor |
| 09h | Write char+attribute at cursor (BL=count) |
| 0Ah | Write char only (no attribute change) |
| 0Eh | Teletype output (AL=char) — simplest "just print a character" call |
| 0Fh | Get current video mode |
| 13h | Write string, no cursor update handling needed |
| 4Fxxh | VESA/VBE extended video (SVGA modes, protected-mode interface) |

Video modes (AL for AH=00h): `0x03` = 80×25 16-color text (the standard DOS
prompt mode), `0x13` = 320×200×256 graphics (the classic demo-scene mode).
[bios.txt:48-101; dos_int_ref.md §6]

**Direct video memory** is often faster than INT 10h for bulk writes:
- Color/VGA text: segment `0xB800`, 2 bytes/cell (`char, attribute`), 80×25.
- Monochrome (MDA/Hercules): segment `0xB000`.
- 256-color graphics mode 0x13: segment `0xA000`, 1 byte/pixel, row-major,
  64000 bytes for 320×200.

## INT 13h — Disk

| AH | Function |
|---|---|
| 00h | Reset disk system |
| 01h | Get status of last operation |
| 02h | Read sectors, CHS addressing (AL=count, CH=cyl, CL=sector, DH=head, DL=drive, ES:BX=buffer) |
| 03h | Write sectors, CHS |
| 04h | Verify sectors |
| 05h | Format track |
| 08h | Get drive parameters |
| 41h | Test for Enhanced Disk Drive (EDD)/LBA support |
| 42h/43h | Read/write, LBA addressing (EDD extension) |

CHS sector numbers are **1-based**, not 0-based — `CL=1` means the first
sector. [bios.txt:103-130; dos_int_ref.md §8]

## INT 14h — Serial port (relevant to this project — see caveat below)

| AH | Function |
|---|---|
| 00h | Initialize port (AL = line-control/baud-rate byte, DX = port 0-3) |
| 01h | Write byte (AL = byte, DX = port) |
| 02h | Read byte (blocks; DX = port) |
| 03h | Get port status |

[bios.txt:132-149]

**`xfercom.asm` does not use INT 14h.** Its header comment mentions "INT
14h/21h and direct UART port I/O" as the conceptual origin (mirroring the
pyc-compiled `xfer.c` predecessor), but the actual NASM code (`uart_init`,
`uart_getc`, `uart_putc` in `xfercom.asm`) programs the 8250 UART registers
directly via `in`/`out` on the port base (`0x3F8` for COM1, etc.) — see
`xfercom.asm:1115-1195`. This is a deliberate choice: INT 14h's baud-rate
byte only encodes a handful of fixed rates and offers no FIFO control,
whereas this project needs an arbitrary runtime-selected baud (any N where
`115200/N` is an integer) and enables/clears the 16550 FIFOs explicitly
(`FCR=0xC7`). Direct port I/O is the only way to get that.

## INT 15h — Miscellaneous system services

| AH/AX | Function |
|---|---|
| 86h | Delay for a microsecond interval |
| 87h | Copy data to extended memory |
| 88h | Get extended memory size (KB) |
| C0h | Detect MCA bus |
| 2400h/2401h/2402h | Disable/enable/get status of A20 gate |
| E820h | Get complete memory map (modern standard, `EAX=0xE820`) |
| E801h | Get contiguous memory size (alternate to E820h) |
| 89h | Switch to protected mode |

[bios.txt:151-201]

## INT 16h — Keyboard

| AH | Function |
|---|---|
| 00h | Get keystroke (blocking; AH=scan code, AL=ASCII) |
| 01h | Check for keystroke (non-blocking; ZF=1 if none waiting) |
| 02h | Get shift-key status |
| 03h | Set typematic (repeat) rate |
| 05h | Push a keystroke into the buffer |
| 10h/11h/12h | Extended versions (needed for function/extended keys with some keyboards) |

`xfercom.asm`'s `uart_getc` polls `AH=0x01` in a loop while waiting for a
serial byte, specifically so the operator can always press **Q** to abort —
the universal escape hatch documented at `xfercom.asm:1146-1173`.

## INT 17h — Parallel port ("printer")

Analogous to INT 14h but for LPT: init, write byte, get status. Not used by
this project (serial only).

## INT 1Ah — RTC / time / PCI

| AH | Function |
|---|---|
| 00h | Get system time (CX:DX = ticks since midnight, BIOS timer) |
| 01h | Set system time |
| 02h/03h | Get/set RTC time (hour/min/sec) — AT-class or later |
| 04h/05h | Get/set RTC date |
| B1xxh | PCI BIOS services (find device, read/write config space) |

18.2 ticks/second is the same IRQ0 rate discussed in [[bare-metal-boot]].
[bios.txt:224-247; dos_int_ref.md §5]

## "Common" vs. exhaustive

The full Ralf Brown's Interrupt List (RBIL) enumerates thousands of
functions, most vendor- or BIOS-specific and obsolete. The tables above are
the "everyone has these" subset per `bios.txt`'s own "Common functions"
section; see [[sources/ralf-brown-interrupt-list]] for how to search RBIL
itself when you need something not listed here. [bios.txt:41-46]

## BIOS availability outside real mode

BIOS functions are **only reliably callable in real mode**. In protected
mode or long mode they're unavailable outright (or require Virtual-8086 mode
/ a temporary drop back to real mode, both with real caveats around IRQ
routing and already-reprogrammed devices like the PIT/PIC). Not relevant to
this DOS-real-mode project directly, but matters if serial-xfer's agent ever
grows a protected-mode component. [bios.txt:271-290]

## See also

- [[dos-int21-api]] — the DOS-level API layered on top of/alongside these BIOS calls
- [[bare-metal-boot]] — boot sequence that sets these interrupt vectors up in the first place
- [[sources/ralf-brown-interrupt-list]] — full RBIL index and how to grep it for anything not covered here
- [[dos-agent]] — `xfercom.asm`'s actual BIOS usage: INT 16h (keyboard abort) only; serial I/O bypasses INT 14h entirely
