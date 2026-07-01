---
title: 8086/8088 CPU Model — Registers, Flags, Addressing
type: concept
sources:
  - docs/raw/1/Programming_the_8086_8088.md (ch. 2 "Inside the 8086/8088", ch. 3 "Memory Organization and Addressing Modes")
  - docs/raw/1/x86-16-bit-register-model.txt
  - docs/raw/1/real-mode.txt
related:
  - "[[8086-instruction-set]]"
  - "[[x86-real-mode]]"
  - "[[bare-metal-boot]]"
  - "[[sources/programming-8086-8088]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

CPU-level model for the 8086/8088: what's inside the chip, how registers and
flags are organized, and the 8086-vs-8088 difference that matters for timing
(not for the instruction set — both run identical code). Companion to
[[8086-instruction-set]] (what the CPU can execute) and [[x86-real-mode]]
(how segmentation turns register values into physical addresses).

## Two functional units

The 8086/8088 internally splits into:
- **BIU** (Bus Interface Unit) — fetches instructions, generates 20-bit
  addresses, manages the prefetch queue.
- **EU** (Execution Unit) — 16-bit ALU, executes instructions, holds the
  general registers and flags.

This split is why prefetching works: the BIU can fetch ahead while the EU
executes. Not architecturally load-bearing for assembly programming, but it
explains why cycle counts in old references don't map 1:1 to wall-clock time.

## General registers

Four 16-bit **data registers**, each splittable into 8-bit halves:

| 16-bit | High byte | Low byte |
|--------|-----------|----------|
| AX | AH | AL |
| BX | BH | BL |
| CX | CH | CL |
| DX | DH | DL |

Four 16-bit **pointer/index registers**, usable only as full 16-bit values
(no high/low split): `SP` (stack pointer), `BP` (base pointer), `SI` (source
index), `DI` (destination index).

[Programming_the_8086_8088.md:834-838]

### Instruction pointer

`IP` replaces the classic "program counter." The BIU updates it to point at
the next instruction. **Programs cannot read or write IP directly** — it can
only be changed indirectly via `CALL`/`JMP`/`RET`/`INT`/`IRET`, or saved/restored
via the stack (an `INT` pushes flags+CS+IP; `IRET` pops them back).
[Programming_the_8086_8088.md:856]

## Segment registers

Four 16-bit segment registers: `CS` (code), `DS` (data), `SS` (stack), `ES`
(extra). Each is combined with a 16-bit offset to form a 20-bit physical
address — see [[x86-real-mode]] for the `segment×16 + offset` arithmetic and
per-register implicit-use table (which instructions default to which segment,
and which — `ES` for string destinations — can't be overridden).
[Programming_the_8086_8088.md:840-852; x86-16-bit-register-model.txt]

## FLAGS register

Six **status flags**, updated by the EU after arithmetic/logic ops, and used
by conditional jumps:

| Flag | Bit | Name | Meaning |
|------|-----|------|---------|
| CF | 0 | Carry | Carry/borrow out of the high-order bit |
| PF | 2 | Parity | Set if low byte of result has an even number of 1 bits |
| AF | 4 | Auxiliary carry | Carry/borrow between low and high nibble (BCD arithmetic) |
| ZF | 6 | Zero | Result was zero |
| SF | 7 | Sign | High-order bit of result (two's-complement sign) |
| OF | 11 | Overflow | Signed result too large for the destination |

Plus three **control flags**, not tied to arithmetic results:

| Flag | Bit | Name | Meaning |
|------|-----|------|---------|
| TF | 8 | Trap | Set → single-step interrupt (INT 1) after every instruction; used by debuggers |
| IF | 9 | Interrupt enable | Clear (via `CLI`) to mask maskable hardware interrupts; `STI` sets it |
| DF | 10 | Direction | Clears (`CLD`) → string ops (`MOVS`/`STOS`/etc.) increment SI/DI; sets (`STD`) → they decrement |

Bit numbers are the standard 8086 FLAGS layout; the book covers the six status
flags' *meaning* in detail but doesn't tabulate bit positions.
[Programming_the_8086_8088.md:858-879]

## 8086 vs 8088: the only difference that matters

Both chips execute **the identical instruction set** — this project's
`cpu 8086` directive is about opcode availability, not which of these two
chips it targets. The difference is the external data bus:

| | 8086 | 8088 |
|---|------|------|
| Address lines | 20 | 20 |
| Data bus width | 16-bit | 8-bit |
| Word access at even address | 1 bus cycle (both bytes at once, `A0`+`BHE` both 0) | 2 bus cycles (always, one byte per cycle) |
| Word access at odd address | 2 bus cycles ("unaligned" penalty) | 2 bus cycles (no penalty vs. even — it's always 2) |

So on the 8086, aligning word data on even addresses is a real speed win; on
the 8088 it makes no difference since every 16-bit access already costs two
bus cycles. Neither point affects correctness — only cycle counts.
[Programming_the_8086_8088.md:893-949]

## Addressing modes (16-bit)

Only `BX`, `BP`, `SI`, `DI` may appear as base/index registers in a memory
operand — **not** `AX`, `CX`, `DX`, `SP`:

| Form | Example |
|------|---------|
| Base only | `[BX]`, `[BP]`, `[SI]`, `[DI]` |
| Base + displacement | `[BX+4]`, `[BP+4]` |
| Base + index | `[BX+SI]`, `[BX+DI]`, `[BP+SI]`, `[BP+DI]` |
| Base + index + displacement | `[BX+SI+4]` |
| Direct address | `[0x1234]` |

`[BP+...]` defaults to the **SS** segment (it's the stack-frame idiom); every
other form defaults to **DS**. [real-mode.txt §Addressing Modes]

## I/O ports (separate address space)

The 8086/8088 use **I/O-mapped I/O**: a separate 64 KB port address space
(only 16 of the 20 address lines are used for I/O), distinct from memory even
though the numeric values can coincide — a control-bus line (`M/IO`)
distinguishes a memory cycle from a port cycle, not the address itself.

- `IN AL, port` / `IN AX, port` — fixed port (8-bit port number, 0–255) or
  variable port (`IN AL, DX` — full 16-bit port number in `DX`).
- `OUT port, AL` / `OUT port, AX` — same two addressing forms, other direction.

`xfercom.asm` uses variable-port `in`/`out` exclusively (`in al, dx` /
`out dx, al`) to bit-bang the 8250 UART directly at ports like `0x3F8`
(COM1) — beyond the fixed-port 0–255 range, so the DX form is mandatory here.
[Programming_the_8086_8088.md:4700-4767; xfercom.asm uart_init/uart_getc/uart_putc]

## See also

- [[8086-instruction-set]] — the instructions themselves, grouped by category,
  with the `cpu 8086` forbidden-instruction list
- [[x86-real-mode]] — segmentation math, COM/EXE layout, calling conventions
- [[bare-metal-boot]] — what state these registers are in before any OS runs
- [[sources/programming-8086-8088]] — chapter map into the source book (OCR caveat)
