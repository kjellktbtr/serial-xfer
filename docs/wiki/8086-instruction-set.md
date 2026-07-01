---
title: 8086 Instruction Set Reference
type: reference
sources:
  - docs/raw/1/8086_instruction_set.html
  - docs/raw/1/Programming_the_8086_8088.md (ch. 4 "The Instruction Set: Individual Descriptions")
related:
  - "[[x86-16bit-cpu]]"
  - "[[sources/nasm-manual]]"
  - "[[dos-agent]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

Instruction set grouped by category, scoped to what `xfercom.asm`'s
`cpu 8086` directive (see `xfercom.asm:26`) actually allows NASM to assemble.
This project's hard constraint — **8086/8088-clean, no 186/286/386
instructions** — means a handful of instructions that "everyone knows" are
actually off-limits here.

## ⚠️ Instructions this raw source lists but the 8086 does NOT have

`docs/raw/1/8086_instruction_set.html` bills itself as "the complete 8086
instruction set," but it includes three 80186+ additions, which it does
flag individually in the body text (just not in the title):

| Instruction | Why it's not 8086 | Source note |
|---|---|---|
| `PUSHA` | Push-all, added on 80186 | "this instruction works only on 80186 CPU and later!" |
| `POPA` | Pop-all, added on 80186 | same |
| `PUSH immediate` (`PUSH 1234h`) | 8086 `PUSH` only takes REG/SREG/memory | "PUSH immediate works only on 80186 CPU and later!" |

**Not flagged by the source, but also not 8086** (common trap — the doc's
"REG, immediate" shift/rotate operand form is only valid when the immediate
is exactly `1`; an arbitrary immediate shift count is an 80186+ encoding):

| Instruction | 8086-legal forms | 80186+-only form |
|---|---|---|
| `SHL`/`SAL`/`SHR`/`SAR`/`ROL`/`ROR`/`RCL`/`RCR` | shift by **1** (implicit), or shift by **CL** | shift by an arbitrary immediate count (e.g. `shl ax, 4`) |

Also absent from 8086 (and correctly absent from this source's list, so no
correction needed): `IMUL reg, r/m, imm` (3-operand form), `INS`/`OUTS`,
`BOUND`, `ENTER`/`LEAVE`. All are 80186+ or later.

**In practice you don't need to memorize this table** — NASM's `cpu 8086`
directive (see [[sources/nasm-manual]]) rejects every one of these at
assemble time with an error. Treat a `cpu 8086` assembly failure on a shift
or push as "I used the wrong shift-count form," not a mystery.

## Data movement

| Instr | Operands | Notes |
|---|---|---|
| `MOV` | reg/mem, reg/mem/imm | Cannot move mem→mem directly |
| `PUSH` / `POP` | reg, sreg, mem | No `PUSH imm` on 8086 (see above) |
| `XCHG` | reg/mem, reg | `XCHG AX, AX` = 1-byte NOP encoding |
| `IN` / `OUT` | fixed port (imm8) or variable port (DX) | See [[x86-16bit-cpu]] I/O ports |
| `XLATB` | (implicit AL, [BX+AL]) | Table lookup / translate |
| `LEA` | reg, mem | Load effective **address**, not the value |
| `LDS` / `LES` | reg, mem (far pointer) | Load reg + segment (DS or ES) from a 32-bit memory pointer |
| `LAHF` / `SAHF` | (implicit) | Load/store low byte of FLAGS via AH |

## Arithmetic

| Instr | Operands | Notes |
|---|---|---|
| `ADD` / `ADC` | reg/mem, reg/mem/imm | ADC includes carry-in |
| `SUB` / `SBB` | reg/mem, reg/mem/imm | SBB includes borrow-in |
| `INC` / `DEC` | reg/mem | Does **not** affect CF (only ADD/SUB family does) |
| `NEG` | reg/mem | Two's-complement negate |
| `CMP` | reg/mem, reg/mem/imm | Like SUB but discards the result, sets flags only |
| `MUL` / `IMUL` | reg/mem (1-operand only on 8086) | `AX = AL*op` (byte) or `DX:AX = AX*op` (word) |
| `DIV` / `IDIV` | reg/mem | `AL,AH = AX/op` (byte) or `AX,DX = DX:AX/op` (word); div-by-zero → INT 0 |
| `CBW` / `CWD` | (implicit) | Sign-extend AL→AX / AX→DX:AX (needed before signed DIV) |
| `AAA`/`AAS`/`AAM`/`AAD` | (implicit) | BCD adjust after add/sub/mul, before div |
| `DAA` / `DAS` | (implicit, AL) | Decimal-adjust after add/sub for packed BCD |

## Logic / bit operations

| Instr | Operands | Notes |
|---|---|---|
| `AND` / `OR` / `XOR` | reg/mem, reg/mem/imm | Clears CF and OF |
| `NOT` | reg/mem | Bitwise complement, flags unaffected |
| `TEST` | reg/mem, reg/mem/imm | Like AND but discards result |
| `SHL`/`SAL`, `SHR`, `SAR` | reg/mem, **1 or CL only** | SAR preserves sign bit; SHR does not |
| `ROL`/`ROR`/`RCL`/`RCR` | reg/mem, **1 or CL only** | RCL/RCR rotate through carry |

## String operations

All operate on `[SI]`(source, DS-relative, overridable) and/or `[DI]`
(destination, **ES-relative, never overridable**); direction controlled by
`DF` (`CLD`=forward, `STD`=backward). Prefix with `REP`/`REPE`/`REPNE` to
repeat CX times / while equal / while not equal.

| Instr | Effect |
|---|---|
| `MOVSB` / `MOVSW` | Copy byte/word `[SI]`→`[DI]`, advance SI and DI |
| `CMPSB` / `CMPSW` | Compare `[SI]` vs `[DI]`, set flags, advance both |
| `SCASB` / `SCASW` | Compare AL/AX vs `[DI]`, set flags, advance DI |
| `STOSB` / `STOSW` | Store AL/AX to `[DI]`, advance DI |
| `LODSB` / `LODSW` | Load `[SI]` into AL/AX, advance SI |

`xfercom.asm` does not use the string instruction family — its COBS/CRC
loops are hand-rolled with `lodsb`-style single-register access instead, so
none of these appear in the codebase today, but they're 8086-legal if needed.

## Control transfer

| Instr | Notes |
|---|---|
| `JMP` | Near (intra-segment) or far (inter-segment); register/memory indirect forms allowed |
| `CALL` / `RET` / `RETF` | Near call pushes IP only; far call pushes CS:IP; `RET`/`RETF` pop the same |
| `Jcc` (`JE`,`JNE`,`JG`,`JL`,`JA`,`JB`, …) | Conditional jump on flag combinations; **8-bit signed displacement only** on 8086 (no near-conditional-jump form — that's 386+) |
| `JCXZ` | Jump if CX == 0 (not a flag test) |
| `LOOP` / `LOOPE` / `LOOPNE` (`LOOPZ`/`LOOPNZ`) | Decrement CX, jump if CX≠0 (and optionally ZF condition) |
| `INT` / `INTO` / `IRET` | Software interrupt / interrupt-on-overflow / return from interrupt (pops IP, CS, FLAGS) |
| `HLT` | Halt until next interrupt (rarely useful under DOS) |

`xfercom.asm` leans on the tight 8-bit `Jcc` displacement constantly (all
its `.label` jumps are local, short); this is why the label organization
stays close together — a `cpu 8086` build has no long-conditional-jump escape
hatch the way 386+ code does.

## Flags / processor control

| Instr | Effect |
|---|---|
| `CLC` / `STC` / `CMC` | Clear/set/complement carry flag |
| `CLD` / `STD` | Clear/set direction flag (string op direction) |
| `CLI` / `STI` | Clear/set interrupt-enable flag |
| `NOP` | No operation (1 byte) |
| `LOCK` | Bus-lock prefix (meaningless on a single-CPU DOS box; present for completeness) |

## Flags-affected notation

Source pages mark each instruction's effect on `C Z S O P A` as `1` (forced
set), `0` (forced clear), `r` (result-dependent), blank/`?` (undefined or
unaffected) — e.g. `INC`/`DEC` leave `C` unaffected but set `Z S O P A`
per-result; shift instructions leave `Z S P A` unaffected but set `C` and
(for 1-bit shifts only) `O`. Check the raw source's per-instruction table
when flag behavior matters for a conditional jump immediately afterward.
[8086_instruction_set.html — per-instruction sections]

## See also

- [[x86-16bit-cpu]] — registers, flags bit layout, addressing modes these
  instructions operate on
- [[sources/nasm-manual]] — how `cpu 8086` and `bits 16` interact in NASM
- [[dos-agent]] — where these instructions are used in this project's agent
