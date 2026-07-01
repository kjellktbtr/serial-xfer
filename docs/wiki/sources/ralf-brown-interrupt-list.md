---
title: Ralf Brown's Interrupt List (RBIL) — Index
type: entity
sources:
  - docs/raw/1/ralf_brown_interrupts/dos_int_ref.md
  - docs/raw/1/ralf_brown_interrupts/INTERRUP.PRI
  - docs/raw/1/ralf_brown_interrupts/ (INTERRUP.A through INTERRUP.R, PORTS.A-C, MEMORY.LST, GLOSSARY.LST, TABLES.LST, CATEGORY.KEY)
related:
  - "[[bios-services]]"
  - "[[dos-int21-api]]"
  - "[[bare-metal-boot]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

**Ralf Brown's Interrupt List (RBIL)** is the exhaustive reference for x86
software/hardware interrupts, BIOS functions, and DOS API calls — release 61,
vintage 1990s, still the canonical reference for this domain. It ships as a
set of plain-text files (`INTERRUP.A` through `INTERRUP.R`, ~5 MB total) plus
supporting indexes. [[bios-services]] and [[dos-int21-api]] already distill
the commonly-needed calls; use this page when you need something **not**
covered there.

## What's actually in `docs/raw/1/ralf_brown_interrupts/`

| File(s) | Content |
|---|---|
| `INTERRUP.A` – `INTERRUP.R` | The interrupt list itself, split across 18 files by interrupt-number range (see file map below) |
| `dos_int_ref.md` | A **pre-distilled index** (already absorbed into [[bios-services]] and [[dos-int21-api]] in this wiki) — filtered for 16-bit DOS compiler development, with file+line pointers into `INTERRUP.*` |
| `INTERRUP.PRI` | A primer: what an interrupt is, how IVT-based dispatch works in real mode vs. protected mode vs. V86 mode |
| `MEMORY.LST` | BIOS Data Area (BDA) and memory map reference |
| `GLOSSARY.LST` | Terminology |
| `TABLES.LST` | Master index of cross-referenced data structures (PSP, MCB, DTA, etc.), each tagged with an ID like `#01628` |
| `CATEGORY.KEY` | Category-letter legend (see below) |
| `PORTS.A/B/C` | Hardware I/O port reference (separate from the interrupt list) |
| `OPCODES.LST`, `FARCALL.LST`, `CMOS.LST`, `I2C.LST`, `86BUGS.LST`, `MSR.LST`, `SMM.LST` | Specialized references (CPU opcodes, undocumented far-call entry points, CMOS layout, I2C, known 8086 silicon bugs, model-specific registers, SMM) — niche, grep on demand |

## File map: interrupt number → file

| File | Interrupt range | Covers |
|---|---|---|
| INTERRUP.A | INT 00 – INT 10/BE | CPU exceptions, IRQ handlers, BIOS video |
| INTERRUP.B | INT 10/BF – INT 15/0F | BIOS memory, disk, **serial (INT 14h)**, printer, time, boot |
| INTERRUP.C | INT 15/10 – INT 15/E7 | Extended BIOS |
| INTERRUP.D | INT 15/E8 – INT 1A/B0 | Extended BIOS, keyboard, boot, time |
| INTERRUP.E | INT 1A/B1 – INT 1F | PCI, multiplex |
| INTERRUP.F | INT 20 – INT 21/43 | DOS core: terminate, stdio, FCB, time, date |
| INTERRUP.G | INT 21/44 – INT 21/5E | DOS extended: file I/O, memory, directory, EXEC |
| INTERRUP.H | INT 21/5F – INT 21/E2 | DOS more extended (networking, extended attrs) |
| INTERRUP.I | INT 21/E3 – INT 21/F1 | DOS late extended |
| INTERRUP.J | INT 21/F2 – INT 25 | NetWare, absolute disk read |
| INTERRUP.K | INT 26 – INT 2F/15 | Absolute disk write, multiplex |
| INTERRUP.L–R | INT 2F/16 – INT FF | Multiplex, hardware, vendor-specific |

## Entry format

Each RBIL entry is preceded by a divider line of the form
`--------X-nnnn---...` where:
- Position 7 (1-based) = a **category letter** (see below)
- Positions 9-10 = the interrupt number in hex
- The rest = additional function/subfunction identifiers, then a
  timestamp/version tag

## Category letters (`CATEGORY.KEY`)

| Letter | Category | Letter | Category |
|---|---|---|---|
| A | Applications | D | DOS kernel |
| B | BIOS | S | Serial I/O |
| C | CPU-generated | H | Hardware |
| K | Keyboard enhancers | M | Mouse |
| N | Network | P | Printer enhancements |
| V | Video | m | Memory management |
| ... | *(full list in `CATEGORY.KEY`; ~35 letters total, upper+lowercase distinct)* | | |

## How to search it

```bash
# Find a DOS function by AH value:
grep -n "AH = 3Dh" docs/raw/1/ralf_brown_interrupts/INTERRUP.F

# Find by name/keyword across the DOS-relevant files:
grep -n "FIND FIRST" docs/raw/1/ralf_brown_interrupts/INTERRUP.G

# Read a specific line range once you have one from dos_int_ref.md:
sed -n '6205,6260p' docs/raw/1/ralf_brown_interrupts/INTERRUP.G
```

`dos_int_ref.md` gives approximate line numbers per entry (already reflected
in [[bios-services]]/[[dos-int21-api]]'s tables) — grep is more reliable for
finding *new* entries this wiki hasn't already indexed.

## Cross-referenced data structures (via `TABLES.LST`)

| Structure | Table ID | Primary location |
|---|---|---|
| PSP (Program Segment Prefix) | #01378 | INTERRUP.F:4490 |
| Environment block | #01379 | INTERRUP.F:4578 |
| EXEC parameter block | #01590 | INTERRUP.G:5199 |
| List of Lists (SYSVARS) | #01627 | INTERRUP.G:6371 |
| MCB (Memory Control Block) | #01628 | INTERRUP.G:6487 |
| FindFirst DTA | #01626 | INTERRUP.G:6243 |
| Drive Parameter Block | #01395 | INTERRUP.F:5482 |

## The interrupt primer (`INTERRUP.PRI`)

A short (135-line) conceptual primer, useful background beyond the raw
function tables:

- **Real-address-mode dispatch**: the 8086 multiplies the interrupt number
  by 4 to index the IVT, pushes flags+CS+IP, jumps to the handler; `IRET`
  reverses this. Software interrupts (`INT n`) are indistinguishable from
  hardware ones to the handler, except they're never masked and don't
  trigger a PIC acknowledgement cycle.
- **Protected-mode dispatch** differs: the IDT holds 8-byte descriptors
  (not raw 4-byte addresses), doesn't have to sit at physical address 0, and
  specifies *how* control transfers via three gate types (Interrupt Gate,
  Trap Gate, Task Gate) — Interrupt Gates clear IF automatically, Trap Gates
  don't.
- **V86 mode dispatch**: interrupts in V86 mode always trap to a protected-mode
  supervisor first, which typically "reflects" the interrupt back into V86
  mode by jumping through the real-mode IVT itself, after handling
  whatever it needs to at the supervisor level.

[INTERRUP.PRI:50-107]

## See also

- [[bios-services]] — the pre-distilled "common calls" subset for INT 10h/13h/14h/15h/16h/17h/1Ah
- [[dos-int21-api]] — the pre-distilled subset for INT 21h
- [[bare-metal-boot]] — IVT structure and hooking, which this primer's dispatch mechanics underpin
