# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## Project: serial-xfer

Move files to/from a vintage MS-DOS machine over a plain serial cable and optionally mount its filesystem via FUSE. Three components:

| File | Role |
|------|------|
| `xfercom.asm` → `XFER.COM` | Tiny (≈2.6 KB) hand-written NASM DOS agent; `cpu 8086`, no runtime, no linker |
| `host.py` | Python host: upload/download files, directory listing, COBS+CRC framing |
| `mountfs.py` | Python FUSE mount; eager-crawl cache, write-through I/O |

**Hard constraints:**
- `cpu 8086` — no 186/286/386 instructions in `xfercom.asm`; NASM enforces this.
- Protocol types 1–9 are the **frozen base protocol**. Capabilities beyond v0 are exposed via a version handshake (`T_VERSION=16`). Host asks once at session start; old agents return empty ACK = version 0.
- Keep `XFER.COM` tiny (< 3 KB). Check with `test_size` in `test_com.py`.
- COBS + CRC-16/CCITT framing; whole-file CRC-32; stop-and-wait ACK pacing (see `PROTOCOL.md`).

**Build & test:**
```bash
nasm -f bin xfercom.asm -o XFER.COM          # or: make
uv run --extra dev python test_com.py         # needs nasm + unicorn; emulator-free
```

**Key reference files:**
- `PROTOCOL.md` — wire protocol specification (all packet types, layouts, versioning)
- `PROTOCOL.md` → "Protocol versioning" — explains the T_VERSION handshake
- `docs/wiki/index.md` — master wiki catalog (see below)
- `docs/wiki/log.md` — wiki operation log (append only)
- `log.md` — human-facing project changelog (dated entries)
- `docs/improvements.md` — improvement checklist

## Standing workflow (every session)

Follow this at the end of any session where changes were made or discoveries happened:

1. **Improvements checklist** (`docs/improvements.md`):
   - **Add** any newly noticed issues or ideas as `- [ ] ...` items.
   - **Tick off** (`[ ]` → `[x]`) items you implemented in this session.

2. **Project changelog** (`log.md`):
   - Append a dated entry in the format `## YYYY-MM-DD HH:MM — <summary>` for each change implemented.

3. **Wiki** (`docs/wiki/`):
   - After discovering something non-obvious or implementing a feature, create or update the relevant wiki page (follow conventions in `docs/CLAUDE.md`).
   - Append one line to `docs/wiki/log.md`.
   - Update `docs/wiki/index.md` if a new page was created.

**Two logs, distinct roles:**
- `log.md` = human-facing project changelog (one entry per feature/fix)
- `docs/wiki/log.md` = wiki operation log (one line per wiki page touched)

**Auto-update the wiki when you learn something.** Wiki drift = silent knowledge loss. If you read code to understand something, write it down so the next session doesn't have to re-derive it.
