---
title: DOS INT 21h API Reference
type: reference
sources:
  - docs/raw/1/ralf_brown_interrupts/dos_int_ref.md
  - docs/raw/1/ralf_brown_interrupts/ (INTERRUP.F, INTERRUP.G — full detail; grep as needed)
related:
  - "[[bios-services]]"
  - "[[dos-agent]]"
  - "[[dos-datetime-format]]"
  - "[[sources/ralf-brown-interrupt-list]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

DOS's own API, layered on top of BIOS (see [[bios-services]]). One interrupt,
`INT 0x21`, with the function selected by `AH` (sometimes `AH:AL`). Register
convention throughout: **CF clear = success, CF set = error (AX = error
code)**. `DS:DX` is the most common string/buffer pointer.
[dos_int_ref.md §12 "Register Convention"]

**Calls actually used by `xfercom.asm`** are marked ✅ below — this file's
`do_*` helper routines are thin wrappers one level above these exact `INT 21h`
calls (see `xfercom.asm:1197-1343` for the wrapper code, and [[dos-agent]]
for the code-map).

## Character I/O

| AH | Function | Used here? |
|---|---|---|
| 01h | Read char with echo | |
| **02h** | **Write char** (DL=char) | ✅ `putstr`/`puts`/`.h_raw` — every character the agent prints goes through this |
| 06h | Direct console I/O (DL=0xFF for input poll) | |
| 07h/08h | Read char, no echo | |
| 09h | Write `$`-terminated string (DS:DX) | |
| 0Ah | Buffered line input | |

`xfercom.asm` never uses AH=09h despite it being the "usual" DOS string-print
call — every string is printed one `AH=0x02` character at a time instead
(see `putstr`/`puts` at `xfercom.asm:1345-1387`), because the agent's banner
and messages are built from ASCIZ fragments concatenated at runtime, not
`$`-terminated literals.

## File I/O (handle-based, DOS 2.0+)

| AH | Function | Inputs | Used here? |
|---|---|---|---|
| **3Ch** | Create/truncate file | CX=attrs, DS:DX=name | ✅ `do_open` (O_CREAT path) |
| **3Dh** | Open file | AL=mode (0=R,1=W,2=RW), DS:DX=name | ✅ `do_open` (existing-file path) |
| **3Eh** | Close file | BX=handle | ✅ `do_close` |
| **3Fh** | Read | BX=handle, CX=bytes, DS:DX=buf | ✅ `do_read` |
| **40h** | Write | BX=handle, CX=bytes, DS:DX=buf | ✅ `do_write` (CX=0 truncates — used for PWRITE-with-no-bytes) |
| **41h** | Delete file | DS:DX=name | ✅ `do_delete` (T_DEL) |
| **42h** | Set file position (lseek) | AL=origin (0=start,1=cur,2=end), BX=handle, CX:DX=offset | ✅ `do_lseek` (PREAD/PWRITE) |
| 43h | Get/set file attributes | AL=0 get/1 set, CX=attrs | |
| **56h** | Rename | DS:DX=old, ES:DI=new | ✅ `do_rename` (T_REN) |
| 5Bh/5Ch | Duplicate/force-duplicate handle | | |
| **57h** | Get/set file date+time | AL=0 get/1 set, BX=handle, CX=time, DX=date | ✅ `do_getftime`/`do_setftime` — see [[dos-datetime-format]] for the packed bit layout |

`do_open`'s dispatch on the `O_CREAT` bit (`xfercom.asm:1198-1219`) is a
direct mapping onto whichever of AH=3Ch/3Dh applies.

## Directory operations

| AH | Function | Used here? |
|---|---|---|
| **1Ah** | Set Disk Transfer Area (DTA) pointer (DS:DX) | ✅ `do_setdta`, before any find-first |
| **39h** | Create directory (mkdir) | ✅ `do_mkdir` — treats "access denied" (AX=5) as success (already-exists) |
| **3Ah** | Remove directory (rmdir) | ✅ `do_rmdir` (T_RMD) |
| 3Bh | Change current directory | |
| **4Eh** | Find first matching file (CX=attrs, DS:DX=spec) | ✅ `do_findfirst`, fills the DTA |
| **4Fh** | Find next | ✅ `do_findnext` |

The **DTA** (Disk Transfer Area) is where `4Eh`/`4Fh` write results; its
layout (offsets `0x00`–`0x2A`) is why `xfercom.asm`'s `DTA_ATTR`/`DTA_TIME`/
`DTA_DATE`/`DTA_SIZE`/`DTA_NAME` constants (`xfercom.asm:54-59`) exist —
they're the field offsets into that fixed 128-byte buffer as read directly
by `serve_list`.

### FindFirst DTA layout (relevant offsets)

| Offset | Size | Field |
|---|---|---|
| 0x15h (21) | byte | Attribute |
| 0x16h (22) | word | Packed time |
| 0x18h (24) | word | Packed date |
| 0x1Ah (26) | dword | File size |
| 0x1Eh (30) | 13 bytes | Filename (8.3, NUL-terminated) |

(`dos_int_ref.md` gives these as hex offsets `0Dh/0Fh/13h/.../21h` measured
from a slightly different DTA base convention than `xfercom.asm`'s constants
— both describe the same physical structure; trust the `.asm` constants for
this project's actual buffer layout, cross-check against RBIL's
`INTERRUP.G:6243` for the authoritative field-by-field breakdown if in doubt.)

## Time/date (system clock, not file-specific)

| AH | Function |
|---|---|
| 2Ah/2Bh | Get/set system date |
| 2Ch/2Dh | Get/set system time |

Not used by `xfercom.asm` (it only touches *file* timestamps via AH=57h).
See [[dos-datetime-format]] for the packed-word encoding shared by both the
system clock calls and the file-time calls.

## Program lifecycle

| AH/Int | Function | Used here? |
|---|---|---|
| INT 20h | Terminate (CP/M-style) | |
| 00h | Terminate | |
| **4Ch** | Exit with return code (AL=code) | ✅ `do_quit` (`mov ax, 0x4C00 / int 0x21`) — this is the *only* exit path in the whole agent |
| 4Bh | EXEC — load and run a child program | |
| 25h/35h | Set/get interrupt vector | (see [[bare-metal-boot]] for the no-DOS equivalent) |

`xfercom.asm` never calls `AH=0x4B` (EXEC) or hooks any interrupt vector — a
single flat `.COM` with one exit point, consistent with the "no runtime, no
linker" design goal in `CLAUDE.md`.

## Memory management

| AH | Function |
|---|---|
| 48h | Allocate memory (BX=paragraphs) |
| 49h | Free memory (ES=segment) |
| 4Ah | Resize memory block |
| 58h | Get/set allocation strategy |

Not used — `XFER.COM` is a `.COM` file, so it owns its entire 64 KB segment
already (see `xfercom.asm:1403-1407` — the whole BSS area is just `equ`
offsets past the code, no allocation calls needed at all).

## Error codes (common)

| Code | Meaning |
|---|---|
| 01h | Invalid function number |
| 02h | File not found |
| 03h | Path not found |
| 04h | Too many open files |
| 05h | Access denied |
| 06h | Invalid handle |
| 07h | Insufficient memory |

`do_mkdir`'s "access denied → treat as already-exists" behavior
(`xfercom.asm:1247-1258`) specifically depends on error code `05h` here.

## See also

- [[bios-services]] — BIOS-level calls DOS itself is built on
- [[dos-agent]] — full code-map of how these calls compose into `xfercom.asm`'s handlers
- [[dos-datetime-format]] — packed date/time bit layout used by AH=57h and the DTA
- [[sources/ralf-brown-interrupt-list]] — full RBIL detail (INTERRUP.F/G) for anything not covered here
