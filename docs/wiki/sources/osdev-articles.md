---
title: OSDev/Wikipedia Source Articles — Traceability
type: source-summary
sources:
  - docs/raw/1/real-mode.txt
  - docs/raw/1/x86-16-bit-register-model.txt
  - docs/raw/1/bios.txt
  - docs/raw/1/bios2.txt
  - docs/raw/1/system_init.txt
related:
  - "[[x86-real-mode]]"
  - "[[x86-16bit-cpu]]"
  - "[[bare-metal-boot]]"
  - "[[bios-services]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

Five short OSDev-wiki/Wikipedia articles in `docs/raw/1/` were fully absorbed
into other concept pages rather than getting their own page each (they're
short enough, and their content overlaps enough, that a 1:1 page mapping
would just fragment the same handful of facts). This page is the
traceability index: which raw file fed which wiki page.

| Raw file | Topic | Absorbed into |
|---|---|---|
| `real-mode.txt` | Real mode overview: pros/cons vs. protected mode, memory addressing, addressing modes, protected-mode↔real-mode switching | [[x86-real-mode]] (memory model, addressing modes), [[x86-16bit-cpu]] (addressing-mode register restrictions), [[bare-metal-boot]] (no-protection consequences) |
| `x86-16-bit-register-model.txt` | x86 segmentation mechanics: physical address derivation, segment register roles, protected-mode segment descriptors (80286/80386), practices | [[x86-real-mode]] (segment register table, implicit roles) |
| `bios.txt` | BIOS functions overview: calling convention, INT 10h/13h/14h/15h/16h/1Ah common-function tables, protected-mode/long-mode unavailability | [[bios-services]] (all the per-interrupt tables) |
| `bios2.txt` | BIOS overview (Wikipedia, more historical/infobox-heavy) | Cross-checked against `bios.txt` for [[bios-services]]; mostly redundant with `bios.txt` for this project's purposes |
| `system_init.txt` | x86 system initialization: BIOS boot sequence, bootsector/MBR contract, system "environment" at boot | [[bare-metal-boot]] (entire boot-sequence section) |

## Why no 1:1 pages

Each of these articles is a few hundred lines of general x86/OSDev
background (Wikipedia-style, written for OS-development hobbyists in
general, not for this project specifically). Splitting them into
one-wiki-page-per-raw-file would have meant either near-empty pages or
heavy duplication across `real-mode.txt` and `x86-16-bit-register-model.txt`
(both describe segmentation) and across `bios.txt`/`bios2.txt` (near-total
overlap). Merging into topic-first concept pages ([[x86-real-mode]],
[[x86-16bit-cpu]], [[bare-metal-boot]], [[bios-services]]) keeps facts in one
place per topic instead of scattered by source file.

## See also

- [[x86-real-mode]], [[x86-16bit-cpu]], [[bare-metal-boot]], [[bios-services]] — the actual content pages
