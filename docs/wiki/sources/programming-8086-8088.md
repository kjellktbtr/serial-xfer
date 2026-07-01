---
title: "Programming the 8086/8088" (Sybex, 1983) — Chapter Map
type: source-summary
sources:
  - docs/raw/1/Programming_the_8086_8088.md
related:
  - "[[x86-16bit-cpu]]"
  - "[[8086-instruction-set]]"
created: 2026-07-01
updated: 2026-07-01
confidence: medium
---

## ⚠️ OCR quality caveat — read this first

`docs/raw/1/Programming_the_8086_8088.md` is an OCR conversion of the 1983
Sybex book (Kane, "Programming the 8086/8088"). The OCR is **badly garbled**
in places — section headings, figure captions, and program listings often
have scrambled characters (e.g. a heading rendered as
`## -1 CLD~ClearDirectionFlag----`, or "8086/8088" rendered as "808618088").

**Usable for:** conceptual explanations in flowing prose (register roles,
memory organization concepts, interrupt mechanics, I/O addressing) — the
sentence-level text survived OCR reasonably well.

**Not reliable for:** exact opcode encodings, hex byte sequences in
instruction-reference tables, and anything inside a code/figure caption
where OCR corruption concentrates. For opcode-exact reference, use
[[8086-instruction-set]] (sourced from `8086_instruction_set.html`, a clean
non-OCR reference) instead of this book.

## Chapter map

| Ch | Title | Body line (approx) | Absorbed into |
|---|---|---|---|
| 1 | Basic Concepts | 56+ | (background only, not wiki'd) |
| **2** | **Inside the 8086/8088** — registers, flags, instruction cycle | 800-887 | [[x86-16bit-cpu]] |
| **3** | **8086/8088 Memory Organization and Addressing Modes** | 893-1006+ | [[x86-16bit-cpu]] (bus-width section), [[x86-real-mode]] (addressing modes) |
| 4 | The Instruction Set: Individual Descriptions | 1214-4064 | [[8086-instruction-set]] (cross-checked against the clean HTML source instead — see caveat above) |
| 5 | Basic Programming Techniques (arithmetic, BCD, subroutines) | ~ (not yet wiki'd) | — |
| **6** | **Interrupts for the 8086/8088** | 4462-4685 | [[bare-metal-boot]] (IVT structure, dispatch mechanics) |
| **7** | **Input/Output for the 8086/8088** | 4700-5000+ | [[x86-16bit-cpu]] (I/O ports section) |
| 8 | More Applications Using the IBM PC (BIOS access, RS-232 preamble) | ~241+ (TOC) | Not yet distilled — potential future source for a serial-port-specific concept page |
| 9 | Program Development | ~263+ (TOC) | Not wiki'd (toolchain-era content, superseded by NASM) |

Line numbers are approximate — the book has no clean chapter markers in the
OCR'd markdown (chapter headings collided with the TOC's own `##`/`#`
markup); the ranges above were located by grepping for stable phrases (e.g.
`"INSIDE THE 8086/8088"`, `"WHAT IS AN INTERRUPT?"`) rather than by heading
level.

## Chapter 8 (not yet distilled)

Covers BIOS access, printer I/O preamble, keyboard preamble, and an
"RS-232 preamble" — potentially relevant to a future serial-port-specific
wiki page, since this project's whole purpose is serial I/O, but not yet
read in enough depth to distill reliably. Flagged here rather than silently
skipped; grep the raw file for `"RS-232"` or `"Keyboard Preamble"` if you
need it.

## How to search it

```bash
grep -n -i "search phrase" docs/raw/1/Programming_the_8086_8088.md
sed -n 'START,ENDp' docs/raw/1/Programming_the_8086_8088.md
```

Prefer searching for a stable multi-word phrase over a section-heading
pattern — headings are the most OCR-damaged part of this file.

## See also

- [[x86-16bit-cpu]] — CPU model content distilled from this book
- [[8086-instruction-set]] — instruction reference (uses the cleaner HTML source, not this book, for opcode tables)
- [[bare-metal-boot]] — interrupt mechanics distilled from ch. 6
