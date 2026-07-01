---
title: x86 Real-Mode Programming Guide (16-bit NASM & C)
type: concept
sources:
  - docs/raw/1/nasmdoc.txt
  - docs/raw/1/bios.txt
  - docs/raw/1/system_init.txt
  - docs/raw/1/real-mode.txt
  - docs/raw/1/x86-16-bit-register-model.txt
  - xfercom.asm
related:
  - "[[sources/nasm-manual]]"
  - "[[bios-services]]"
  - "[[bare-metal-boot]]"
  - "[[dos-int21-api]]"
  - "[[x86-16bit-cpu]]"
  - "[[8086-instruction-set]]"
  - "[[dos-agent]]"
created: 2026-06-26
updated: 2026-07-01
confidence: high
---

# x86 Real-Mode Programming Guide (16-bit NASM & C)

Practical reference for writing 16-bit DOS programs and boot-sector code in NASM
(and C compiled with OpenWatcom or pyc). Cross-references the full sources in this repo.

---

## Memory Model

Physical address = **segment × 16 + offset** (both 16-bit).

- Maximum addressable: 1 MB + 64 KB - 16 bytes (A20 gate allows 0x10FFEF).
- Each segment covers exactly 64 KB (offset wraps at 0xFFFF).
- Segments can overlap freely; two far pointers to the same byte are **not** equal
  unless normalised.

**Normalise a far pointer:** `seg = (seg + off>>4) & 0xFFFF; off &= 0x000F`

---

## NASM Directives for Real-Mode

```nasm
bits 16              ; tell NASM all code is 16-bit
```

Always put `bits 16` at the top of every real-mode file. Without it NASM defaults to
whatever the output format demands (often 32-bit for ELF).

### ORG values

| Program type | ORG | Why |
|---|---|---|
| Boot sector | `org 0x7C00` | BIOS loads here |
| COM program | `org 0x100` | PSP occupies first 256 bytes |
| EXE program | `org 0` (per segment) | Linker adds relocations |
| Standalone binary | whatever load address | |

---

## COM Programs

- Flat binary, max 64 KB total (code + data + stack).
- PSP is at offset 0x00–0xFF; code/data start at 0x100.
- At entry: CS=DS=ES=SS=PSP segment, SP=0xFFFE, IP=0x0100.
- Stack is at the end of the 64 KB segment by default.

```nasm
bits 16
org 0x100

section .text

_start:
    mov ah, 0x09          ; DOS print string
    mov dx, hello
    int 0x21
    mov ax, 0x4C00        ; DOS exit, code 0
    int 0x21

section .data
hello db 'Hello, DOS!', 13, 10, '$'
```

Assemble: `nasm -f bin -o HELLO.COM hello.asm`

---

## EXE Programs

- MZ format (magic bytes `MZ` at offset 0).
- Header contains relocation table; linker patches segment references.
- Entry: DS=ES=PSP segment; CS:IP and SS:SP from header.
- Multiple segments allowed; each up to 64 KB.

This project (serial-xfer) builds `XFER.COM` as a `.COM` file only, directly
via the `bin` output format — no linker, no `.EXE`:

```bash
nasm -f bin xfercom.asm -o XFER.COM
```

See [[dos-agent]] for the actual build/test commands and [[sources/nasm-manual]]
for why `.bss` items cost no file bytes in this format.

---

## Segment Register Conventions

In a typical DOS COM program all four segment registers start equal.
For hand-written EXE programs establish them explicitly:

```nasm
mov ax, cs          ; or use your data segment label
mov ds, ax
mov es, ax
; SS:SP set up by DOS from EXE header
```

**You cannot `mov ds, imm16`** — you must go through a general register:
```nasm
mov ax, seg my_data_seg
mov ds, ax
```

---

## Stack

- Stack grows **downward** in real mode (same as all x86 modes).
- `PUSH` decrements SP by 2, stores word; `POP` loads word, increments SP.
- In COM programs the initial SP=0xFFFE (word before the segment's top byte).
- Minimum practical stack for a DOS program: ~256 bytes. Games need more (1–4 KB).

```nasm
; Reserve 512-byte stack in a COM program (redundant but shows the pattern):
section .bss
    resb 512
stack_top:
```

---

## Calling BIOS (INT 0x10 / 0x13 / 0x16 …)

```nasm
; Print character via BIOS teletype
mov ah, 0x0E
mov al, 'X'
mov bh, 0          ; page
int 0x10
```

Check carry flag on disk calls:

```nasm
mov ah, 0x02        ; read sectors CHS
mov al, 1           ; 1 sector
mov ch, 0           ; cylinder 0
mov cl, 1           ; sector 1 (1-based!)
mov dh, 0           ; head 0
mov dl, 0x00        ; drive A:
mov bx, buffer      ; ES:BX = destination
int 0x13
jc  disk_error
```

Full BIOS function reference: [[bios-services]].

---

## Calling DOS (INT 0x21)

```nasm
; Write string to stdout
mov ah, 0x40        ; write to file handle
mov bx, 1           ; handle 1 = stdout
mov cx, 5           ; byte count
mov dx, msg         ; DS:DX = buffer
int 0x21
jc  write_error

; Exit
mov ax, 0x4C00
int 0x21
```

Full INT 21h reference: [[dos-int21-api]].

---

## Calling Conventions (C ↔ NASM interop)

When linking NASM objects with OpenWatcom C (`-ms` small model):

| Convention | Watcom default (small model) |
|---|---|
| Calling type | `__cdecl` or Watcom register-based (`__watcall`) |
| Param passing | right-to-left on stack (cdecl) or AX/BX/CX/DX (watcall) |
| Return value | AX (16-bit), DX:AX (32-bit) |
| Caller cleans stack | yes (cdecl) |
| Preserved by callee | BP, SI, DI, DS, SS |

In NASM, preserve **BP, SI, DI** across any function callable from C.

`xfercom.asm` doesn't use this convention at all — it has no C interop and no
linker step. Its internal calling convention is documented in the file's own
header comment (`xfercom.asm:22-24`): arguments in registers, every helper
preserves all registers except its result. See [[dos-agent]].

---

## Interrupts in Real Mode

The **IVT** (Interrupt Vector Table) lives at physical 0x0000–0x03FF: 256 entries of
4 bytes each (2-byte offset + 2-byte segment, little-endian).

```
physical address of handler for INT n = *(DWORD*)(n * 4)
```

**Hook an interrupt (save old, install new):**

```nasm
; Save old INT 9 (keyboard) handler
mov ah, 0x35
mov al, 0x09
int 0x21           ; ES:BX = old handler

mov [old_kbd_seg], es
mov [old_kbd_off], bx

; Install new handler
mov ah, 0x25
mov al, 0x09
mov dx, new_handler   ; DS:DX = new handler
int 0x21
```

Restore before program exits — unhooking is mandatory for TSRs that terminate.

---

## I/O Ports

Direct port I/O works in real mode without any privilege ring checks.

```nasm
in  al, 0x60        ; read keyboard scancode from port 0x60
out 0x20, al        ; send EOI to master PIC (port 0x20)
```

Useful ports for DOS real-mode programs:

| Port | Purpose |
|------|---------|
| 0x20 / 0x21 | Master PIC (command / data) |
| 0x40–0x43 | PIT (Programmable Interval Timer) |
| 0x60 | Keyboard data |
| 0x64 | Keyboard status/command |
| 0x3D4 / 0x3D5 | CRT controller (cursor position etc.) |
| 0x3C8 / 0x3C9 | VGA DAC (palette write) |

---

## Video RAM Direct Access

**Text mode** (80×25, INT 0x10 mode 0x03):
- Segment **0xB800**, 4000 bytes, 2 bytes per cell: `[char][attr]`.
- Attribute byte: bits 7–4 = background colour, bits 3–0 = foreground colour.

```nasm
mov ax, 0xB800
mov es, ax
mov word [es:0], 'A' | (0x0F << 8)  ; white 'A' on black at top-left
```

**Graphics mode** (320×200×256, INT 0x10 mode 0x13):
- Segment **0xA000**, 64000 bytes, 1 byte per pixel, row-major.

```nasm
mov ax, 0xA000
mov es, ax
mov byte [es: row*320 + col], colour
```

---

## Useful NASM Snippets

### Print ASCIZ string via INT 21h AH=0x09 (must end with `$`)

```nasm
print_str:          ; DS:DX = '$'-terminated string
    mov ah, 0x09
    int 0x21
    ret
```

### Print a single digit (0–9)

```nasm
    mov ah, 0x02
    mov dl, al
    add dl, '0'
    int 0x21
```

### Read a key without echo

```nasm
    mov ah, 0x07
    int 0x21        ; AL = ASCII code
```

### Delay ~1 second (18 timer ticks)

```nasm
    mov cx, 0
    mov dx, 18
    mov ah, 0x86    ; BIOS delay: CX:DX = microseconds? No — use INT 1A:
    ; Actually: INT 0x1A AH=0x00 reads ticks; loop until N ticks elapsed
```

### Convert BX to 4-digit hex string

```nasm
hex_out:
    mov cx, 4
.loop:
    rol bx, 4
    mov al, bl
    and al, 0x0F
    add al, '0'
    cmp al, '9'
    jbe .ok
    add al, 7       ; 'A'–'9' gap
.ok:
    mov ah, 0x02
    mov dl, al
    int 0x21
    loop .loop
    ret
```

---

## Common Pitfalls

1. **Forgetting `bits 16`** — NASM silently emits 32-bit encoding; wrong opcodes.
2. **INT values in decimal** — `int 10` is INT 0x0A (LF), not INT 0x10 (video).
3. **Segment arithmetic** — adding more than 0xFFFF to an offset doesn't wrap the segment; you must normalise manually.
4. **`org` in multi-section NASM binary** — `org` sets the base of the *current section*; for COM use a single flat file.
5. **Not preserving BX/SI/DI across BIOS calls** — BIOS promises to preserve all *other* registers, but some buggy BIOSes (notably early Bochs) trash upper 16 bits of 32-bit registers.
6. **DS not set after far call / interrupt** — interrupts save CS:IP+flags but not DS. If your ISR needs DS, push and restore it explicitly.
7. **Stack not aligned** — not a real-mode concern (unlike 32/64-bit), but a 1-byte `resb` in `.bss` before the stack can cause confusing off-by-one bugs.

---

## Quick Reference Card

| Goal | Mechanism |
|------|-----------|
| Print char | INT 0x10 AH=0x0E or INT 0x21 AH=0x02 |
| Print `$`-string | INT 0x21 AH=0x09, DS:DX |
| Read key | INT 0x21 AH=0x07 (no echo) or 0x01 |
| Open file | INT 0x21 AH=0x3D |
| Write file | INT 0x21 AH=0x40 |
| Alloc memory | INT 0x21 AH=0x48, BX=paragraphs |
| Exit | INT 0x21 AX=0x4C00 |
| Read disk CHS | INT 0x13 AH=0x02 |
| Set video mode | INT 0x10 AH=0x00, AL=mode |
| Get memory map | INT 0x15 EAX=0xE820 |
| Hook interrupt | INT 0x21 AH=0x25 / 0x35 |
| Get ticks | INT 0x1A AH=0x00 → CX:DX |

---

## See Also

- [[bios-services]] — full BIOS interrupt tables with all sub-functions
- [[dos-int21-api]] — full INT 21h table with error codes and data structures
- [[sources/nasm-manual]] — indexed NASM manual, direct line-number lookup
- [[x86-16bit-cpu]] — register/flags/addressing-mode model underlying this guide
- [[8086-instruction-set]] — instruction reference, with the `cpu 8086` forbidden-instruction list
- [[bare-metal-boot]] — boot sequence and IVT, for programming without DOS at all
- [[dos-agent]] — this project's actual `.COM` agent (`xfercom.asm`), as a worked example
