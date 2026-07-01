---
title: DOS Agent (XFER.COM)
type: code-map
sources:
  - xfercom.asm
related:
  - "[[wire-protocol]]"
  - "[[cobs-framing]]"
  - "[[crc-checks]]"
  - "[[dos-datetime-format]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

## Overview

`xfercom.asm` assembles to a flat 16-bit COM (`nasm -f bin xfercom.asm -o XFER.COM`). Runs on any PC-DOS/MS-DOS/FreeDOS machine with an 8088 or later CPU. No runtime, no linker, no external libraries. Target size < 3 KB.

## Key constraints

- `cpu 8086` at the top of the file — NASM enforces no 186/286/386 instructions. No PUSHA (186), no IMUL with immediate, etc.
- COBS + CRC-16/CCITT per packet; whole-file CRC-32; stop-and-wait ACK pacing.
- Polled UART — no interrupts. Reads LCR/LSR at `[v_base+3/5]`, data at `[v_base]`.

## Entry point and main loop

- `start:` (0x100): calls `parse_args` → `uart_init` → prints banner → enters `.main_loop`
- `.main_loop`: calls `read_frame` → CRC-16 check → dispatch on `v_type`
- Bad CRC → sends NAK, resumes loop

## Dispatch chain (`.crc_ok`)

Linear `cmp al, Txx / je .h_xx` chain, falls through to default empty-ACK.
Types handled: OPEN(1), DATA(2), CLOSE(3), GET(5), LIST(7), MKDIR(6), MSG(9), RAW(15), DEL(10), RMD(11), REN(12), PREAD(13), PWRITE(14), QUIT(4), VERSION(16).

## Key handlers

| Handler | Action |
|---------|--------|
| `.h_open` | AH=3Ch (create/truncate) → `v_fd`, resets `v_wcrc` |
| `.h_data` | AH=40h write at cursor, accumulates `v_wcrc` CRC-32 |
| `.h_close` | Compares expected CRC-32 (pk+2..5); if v1 (dlen≥8) reads time(pk+6..7)+date(pk+8..9) and calls `do_setftime` before close |
| `.h_get` → `serve_get` | Opens file (AH=3Dh), streams DATA packets, reads mtime with `do_getftime` at EOF before close, appends time+date to CLOSE payload (v1: 8 bytes instead of 4) |
| `.h_list` → `serve_list` | `find_first`/`find_next` (INT 21h 4Eh/4Fh); ENTRY payload: attr(1) size(4) time(2 LE) date(2 LE) name |
| `.h_version` | Replies ACK + [0x01] (protocol version 1) |

## UART helpers

- `uart_init` — sets baud divisor via `v_div`, FIFOs on, IRQs off
- `uart_putc(AL)` — waits on LSR bit 5 (THRE), then OUT to `[v_base]`
- `uart_getc` → AL — waits on LSR bit 0 (DR), then IN from `[v_base]`

## INT 21h file helpers

Located in the "v2 INT 21h helpers" block:

| Helper | INT 21h | Notes |
|--------|---------|-------|
| `do_open(DX, BX)` | 3Ch/3Dh | BX flags: bit 8 = O_CREAT |
| `do_close(BX)` | 3Eh | |
| `do_read(BX, DX, CX)` | 3Fh | |
| `do_write(BX, DX, CX)` | 40h | CX=0 truncates |
| `do_lseek(BX, CX:DX)` | 42h (SEEK_SET) | |
| `do_getftime(BX)` | 57h AL=0 | → CX=time, DX=date |
| `do_setftime(BX, CX, DX)` | 57h AL=1 | BX=handle, CX=time, DX=date |
| `do_delete(DX)` | 41h | |
| `do_rmdir(DX)` | 3Ah | |
| `do_rename(DX, DI)` | 56h | ES=DS |
| `do_mkdir(DX)` | 39h | |
| `do_setdta(DX)` | 1Ah | |
| `do_findfirst(DX, CX)` | 4Eh | |
| `do_findnext` | 4Fh | |

## BSS layout

All buffers are `equ` constants (no emitted bytes). Segment base = 0, org=0x100, so absolute addresses.

```
v_fd v_wcrc v_n v_got16 v_type v_seq v_dlen v_status v_name
v_rfd v_rcrc v_dseq v_got v_ftime(dword)
rxf(600) pk(600) tx(600) op(600) fbuf(128) eb(32) dta(128)
v_base v_div v_com v_baud32 v_baudstr v_baudstr_buf
```

`eb` is 32 bytes; v1 ENTRY payload uses up to 9+14=23 bytes (safe margin).

## CLI parsing (parse_args)

PSP at segment 0; command tail at 0x81, length at 0x80. Reads baud (decimal digits) and optional COM number (1..4). Defaults: 9600 baud, COM1 (0x3F8). Prints usage and exits on invalid input. **Tests must write `bytes([0, 0x0D])` to address 0x80 to simulate "no args"** — Unicorn zeroes memory, and a null byte there would fail parse_args.

## Testing

`test_com.py` uses Unicorn to run the actual 16-bit code with INT 21h hooked to an in-memory DOS (`_FakeDos`). The `_boot()` function sets up a full session including `query_version()`. Direct routine tests (`test_codecs`, `test_framing`) must pre-initialize `v_base=0x3F8` since `parse_args` doesn't run.
