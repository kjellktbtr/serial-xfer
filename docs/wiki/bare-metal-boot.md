---
title: Bare-Metal Boot — Programming Without DOS
type: concept
sources:
  - docs/raw/1/system_init.txt
  - docs/raw/1/bios2.txt
  - docs/raw/1/real-mode.txt
related:
  - "[[bios-services]]"
  - "[[x86-16bit-cpu]]"
  - "[[x86-real-mode]]"
  - "[[sources/osdev-articles]]"
created: 2026-07-01
updated: 2026-07-01
confidence: medium
---

How a real-mode program runs **before or without DOS** — bootstrap sequence,
the exact machine state you inherit at a boot sector, and the interrupt
vector table you can hook. serial-xfer doesn't currently boot bare metal
(`XFER.COM` runs under DOS), but this is the reference for anyone extending
the project toward a standalone boot-floppy agent or bringing up new
hardware without an OS.

## Boot sequence (BIOS path)

1. **CPU reset** — fetches the first instruction from the top of the 4 GB
   address space, where ROM is mapped; this ROM contains BIOS init code (up
   to 256 KB). Not observable or controllable by an OS/bootloader author.
2. **RAM detection + BIOS data areas** — BIOS detects installed RAM, does a
   basic memory test, then populates the **BDA** (BIOS Data Area, physical
   `0x0400`–`0x04FF`), the **EBDA**, and the 64 KB "BIOS area"
   (`0xF0000`–`0xFFFFF`). It also sets up the **real-mode IVT** at physical
   `0x0000`–`0x03FF` and a small temporary stack.
3. **Hardware detection/init** — BIOS enumerates and configures every bus
   and device it knows about, using values it chooses (not always optimal —
   an OS may need to reconfigure things later).
4. **Boot device selection** — BIOS walks a CMOS-stored device order,
   testing each for a valid boot sector, until it finds one or gives up.
5. **Bootstrap** — BIOS loads **512 bytes** from the boot device to physical
   address `0x7C00`. If the last two bytes are `0x55 0xAA`, it's treated as
   valid and control jumps to `0x7C00`. Otherwise BIOS tries the next device
   in the list (or locks up with an error if none work).

[system_init.txt:9-22]

## Machine state at `0x7C00`

The only things guaranteed at boot-sector entry:

- **CS:IP** such that execution starts at physical `0x7C00` (in practice
  often `0000:7C00`, but not contractually guaranteed to be that exact
  segment:offset split — normalize if you care).
- CPU is in **16-bit real mode**.
- **DL** = boot drive number (floppy: `0x00`/`0x01`; hard disk: `0x80`+).
- Only those 512 bytes of the boot sector have been loaded — nothing else
  is in memory yet; your bootstrap code has to load the rest itself.

Everything else (DS, ES, SS, SP, other general registers) is **not
standardized** — set them yourself before relying on them.
[system_init.txt:38-45]

A vanishingly small number of ancient BIOSes reportedly start in protected
mode instead; the practical recommendation from the source is simply not to
support those. [system_init.txt:44]

## MBR vs. direct bootsector

Hard disks (and anything emulating one) go through an extra layer: the BIOS
loads and runs the **MBR** (Master Boot Record) at `0x7C00`, which then finds
the "active" partition (flag byte `0x80`) in its embedded partition table and
loads *that* partition's boot sector — again at `0x7C00`, again passing
`DS:SI` → a copy of the partition table entry. Floppies and other
non-partitioned media skip this layer; the OS-specific bootloader loads
directly. CDs/DVDs boot from LBA 17 instead of LBA 0.
[system_init.txt:24-77]

## Interrupt Vector Table (IVT)

Lives at physical `0x0000`–`0x03FF`: 256 entries × 4 bytes, each entry
`offset(2) segment(2)` (little-endian), addressed as `handler = *(DWORD*)(n*4)`.
This is the same IVT the BIOS just finished setting up in step 2 above — by
the time your bootstrap code runs, `INT 0x10`/`0x13`/`0x16`/etc. are already
wired to the BIOS's own handlers. See [[bios-services]] for what's callable
through it, and [[x86-16bit-cpu]] for the FLAGS-push / CS:IP-push mechanics
of `INT`/`IRET`.

**Hooking an interrupt outside DOS** (no `INT 21h AH=25h/35h` available yet)
is direct memory manipulation:

```nasm
; Hook INT 0x08 (timer tick) — save old vector, install new one, no DOS needed
cli
xor ax, ax
mov es, ax                  ; ES = 0 (IVT segment)
mov bx, 0x08 * 4            ; vector offset for INT 8
mov ax, [es:bx]             ; save old offset
mov [old_offset], ax
mov ax, [es:bx+2]           ; save old segment
mov [old_segment], ax
mov word [es:bx], new_handler
mov word [es:bx+2], cs      ; assumes handler is in the same segment as this code
sti
```

Contrast with [[dos-int21-api]]'s `INT 21h AH=25h`/`35h` (set/get interrupt
vector) — those exist specifically so DOS programs don't have to poke the
IVT directly; outside DOS, direct IVT writes are the only option.

## System timer

- **IRQ0 / INT 08h**: hardware timer, fires **18.2 times/second**.
- **INT 1Ch**: a "user tick" hook — the default INT 08h handler chains to
  INT 1Ch after its own bookkeeping, specifically so TSRs and bare-metal code
  can hook a timer callback without replacing the BIOS's own IRQ0 handler.
- BDA offset `0x006C` (a DWORD) holds ticks-since-midnight; each tick ≈ 54.9 ms.

[docs/raw/1/ralf_brown_interrupts/dos_int_ref.md §9 "System Timer"]

## No memory protection

Real mode has no privilege rings, no GDT/paging — any code can retarget any
segment register and touch any physical address. This is what makes direct
IVT hooking (above) and direct video-memory writes (see [[x86-16bit-cpu]])
possible without any OS cooperation, and also why a bug can corrupt anything,
including the BIOS's own data structures in low memory. [real-mode.txt §Cons]

## See also

- [[bios-services]] — the BIOS interrupt services available once boot is done
- [[x86-16bit-cpu]] / [[x86-real-mode]] — the CPU and memory model underneath all of this
- [[sources/osdev-articles]] — traceability back to the raw OSDev/Wikipedia source articles
