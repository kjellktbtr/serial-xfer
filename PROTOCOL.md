# serial-xfer wire protocol

A compact, binary-safe, stop-and-wait protocol between the **host** (`host.py` /
`mountfs.py`) and the DOS **agent** (`XFER.COM`, built from `xfercom.asm`) over a
serial line. This document is the reference for anyone debugging the link or
porting the agent to another platform/compiler.

## Layers

```
serial byte stream   COM1, 9600 baud, 8 data bits, no parity, 1 stop bit (8N1)
  └─ frame           COBS(packet) + 0x00          ; 0x00 is the ONLY delimiter
       └─ packet     TYPE(1) SEQ(1) DATA(0..n) CRC16(2, big-endian)
            └─ CRC16  CRC-16/CCITT, poly 0x1021, init 0xFFFF, over TYPE+SEQ+DATA
```

The UART is driven directly (polled 8250/16550 at I/O base 0x3F8); no interrupts.

### COBS framing

[Consistent Overhead Byte Stuffing](https://en.wikipedia.org/wiki/Consistent_Overhead_Byte_Stuffing)
removes every `0x00` byte from the encoded packet, so a single `0x00` can delimit
frames unambiguously and the payload is **fully binary-safe** (files with embedded
NULs transfer fine). Overhead is 1 byte plus 1 per 254 non-zero bytes.

The receiver reads bytes until it sees a `0x00`, COBS-decodes the rest into the
packet, then validates the CRC-16 (see `read_frame` / `cobs_decode` in the agent
and `cobs_decode` / `parse_packet` in `host.py`).

### Per-packet CRC-16

`CRC-16/CCITT` (poly `0x1021`, init `0xFFFF`, no reflection, no final XOR), computed
over `TYPE SEQ DATA` and appended **big-endian**. A frame whose CRC doesn't match
is answered with `NAK` and retransmitted.

### Whole-file CRC-32

Independently of the per-packet CRC, each file carries a **CRC-32** (reflected
poly `0xEDB88320`, identical to Python's `zlib.crc32`) so a completed transfer is
verified end to end:

- **Upload:** the host puts the file's CRC-32 in the final `CLOSE` packet's DATA
  (4 bytes, big-endian). The agent compares it to the CRC it accumulated while
  writing and returns the verdict in the `CLOSE`-ACK status byte (`0` = OK).
- **Download:** the agent puts the CRC-32 of what it sent in its `CLOSE`; the host
  checks it.

### Pacing (stop-and-wait)

The sender transmits one packet and waits for `ACK<seq>` before sending the next.
A bad per-packet CRC yields `NAK` and the sender resends (also on timeout). Because
it is strictly request/response, the polled UART never has to buffer a stream — it
stays reliable even on slow/marginal links. `SEQ` is a single byte (wraps at 256),
which is plenty for stop-and-wait.

## Packet types

`TYPE` is one byte. Types **1–9** are the frozen base protocol; **10–15** are the
v2 additions (delete/rename/byte-range I/O + raw screen output). `ACK`/`NAK` are
the agent's replies.

### Host → agent

| Type | Name   | # | DATA layout |
|------|--------|---|-------------|
| OPEN   | create/truncate a file for upload | 1  | `name` (ASCII, ≤ ~64) |
| DATA   | a file chunk (upload)             | 2  | up to 128 raw bytes |
| CLOSE  | end of upload                     | 3  | `crc32` (4 bytes, big-endian) |
| QUIT   | tell the agent to exit            | 4  | — |
| GET    | start a download                  | 5  | `name` |
| MKDIR  | create a directory                | 6  | `path` |
| LIST   | directory listing                 | 7  | `spec` (e.g. `C:\DOS\*.*`) |
| MSG    | print text on the DOS screen + CRLF | 9 | `text` |
| DEL    | delete a file                     | 10 | `name` |
| RMD    | remove a directory                | 11 | `path` |
| REN    | rename                            | 12 | `old` `\0` `new` |
| PREAD  | ranged read                       | 13 | `offset`(4, LE) `length`(2, LE) `name` |
| PWRITE | ranged write                      | 14 | `offset`(4, LE) `name` `\0` `bytes` |
| RAW    | print text on the DOS screen **verbatim** (no added CRLF) | 15 | `bytes` |

### Agent → host

| Type | Name | # | DATA layout |
|------|------|---|-------------|
| ENTRY | one directory entry (reply to LIST) | 8 | `attr`(1) `size`(4, LE) `name` (ASCIIZ, ≤14) |
| ACK   | acknowledge                          | 0x10 | optional payload (see below) |
| NAK   | bad CRC, please resend               | 0x11 | — |

Plus `DATA` + `CLOSE` (types 2/3) sent **agent → host** while serving a `GET`
download or a `LIST`. Every exchange is paced by an `ACK` in the other direction.

### ACK payloads

Most commands are acknowledged with an empty `ACK`. A few carry data:

- `CLOSE` (upload) → `ACK` with a 1-byte **status** (`0` = whole-file CRC-32 OK,
  `1` = mismatch).
- `DEL` / `RMD` / `REN` / `PWRITE` → `ACK` with a 1-byte status (`0` = OK).
- `PREAD` → `ACK` whose DATA **is the bytes read** (0 bytes = EOF / open error).

## Notable details

- **Ranges are ≤128 bytes/packet.** `PREAD`/`PWRITE` move at most `CHUNK` (128)
  bytes per request; the host loops, advancing the offset, for larger reads/writes.
- **Zero-length PWRITE = truncate/create.** A `PWRITE` with no `bytes` opens (or
  creates) the file, seeks to `offset`, and issues a 0-byte DOS write, which sets
  EOF there — used for `create_empty` (offset 0) and `truncate(length)`.
- **`LIST` / `ENTRY`.** The agent enumerates `spec` with DOS `find_first`/
  `find_next` (INT 21h 4Eh/4Fh) into a Disk Transfer Area and emits one `ENTRY`
  per match: `attr` is the DOS attribute byte (bit `0x10` = directory), `size` is
  the little-endian file size, `name` is the (≤14-char) ASCIIZ 8.3 name. `.` and
  `..` are included; the host skips them.
- **No timestamps.** `ENTRY` has no date/time field, so mounted files get
  synthesized stat times.
- **8.3 names.** All names are DOS 8.3 (≤12 chars). The host mangles long/illegal
  host filenames to unique upper-case 8.3 names (Windows-9x `~N` scheme).

## Worked example: `OPEN "A.TXT"`

```
packet  = 01 00 41 2E 54 58 54 <crchi> <crclo>     ; TYPE=OPEN SEQ=0 "A.TXT" CRC16
COBS    = <code...> (no 0x00 bytes remain)
frame   = COBS(packet) + 00
```
The agent decodes it, opens `A.TXT` for writing, and replies `ACK` SEQ 0
(`10 00 <crc16> 00` after COBS). The host then streams `DATA`/`CLOSE`.

## Porting the agent

To reimplement the agent on another DOS toolchain (or another platform), you need:
COBS encode/decode, CRC-16/CCITT, CRC-32 (zlib variant), a polled UART driver
(8N1 9600), and the dispatch loop above over INT 21h file/dir calls. The reference
is `xfercom.asm` (hand-written NASM, ~2 KB); `test_com.py` exercises every routine
against `host.py`, so it doubles as a conformance suite.
