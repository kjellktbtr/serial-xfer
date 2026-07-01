---
title: Wire Protocol
type: source-summary
sources:
  - PROTOCOL.md
related:
  - "[[cobs-framing]]"
  - "[[crc-checks]]"
  - "[[dos-agent]]"
  - "[[host-tool]]"
  - "[[protocol-versioning]]"
  - "[[dos-datetime-format]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

## Framing layer

Every message (packet) is wrapped in [[cobs-framing]]:

```
[COBS-encoded(header + payload + CRC16)] 0x00
```

Header (2 bytes, inside COBS): `type(1) seq(1)`. Payload (0–512 bytes). CRC-16/CCITT over header+payload. Delimiter: `0x00` byte (never appears inside COBS frame).

See [[crc-checks]] for CRC details.

## Packet types

All types are frozen-base (v0). V1 extensions add payload fields; old agents ignore them gracefully.

### Host → Agent

| Type | Name | Value | Payload |
|------|------|-------|---------|
| OPEN | Open file for write | 1 | filename (ASCIIZ) |
| DATA | File data chunk | 2 | raw bytes (≤512) |
| CLOSE | End upload | 3 | `crc32(4 BE)` [v1: `+ fat_time(2 LE) fat_date(2 LE)`] |
| QUIT | Disconnect | 4 | — |
| GET | Download file | 5 | filename (ASCIIZ) |
| MKDIR | Create directory | 6 | path (ASCIIZ) |
| LIST | List directory | 7 | glob (ASCIIZ), e.g. `C:\FILES\*` |
| DEL | Delete file | 10 | path (ASCIIZ) |
| RMD | Remove directory | 11 | path (ASCIIZ) |
| REN | Rename | 12 | `old\0new\0` |
| PREAD | Partial read | 13 | `offset(4 LE) length(4 LE) path(ASCIIZ)` |
| PWRITE | Partial write | 14 | `offset(4 LE) data(…)` |
| RAW | Serial passthrough | 15 | raw bytes |
| VERSION | Query protocol version | 16 | — |

### Agent → Host

| Type | Name | Value | Payload |
|------|------|-------|---------|
| ACK | Acknowledge | 0 | *varies by request* |
| NAK | Negative ack | 127 | — |
| ENTRY | Directory entry | 8 | see below |
| MSG | Log message | 9 | text |

### ENTRY payload layout

**v0** (old agent):
```
attr(1) size(4 LE) name(ASCIIZ)
```

**v1** (new agent, `proto_version ≥ 1`):
```
attr(1) size(4 LE) fat_time(2 LE) fat_date(2 LE) name(ASCIIZ)
```

The host determines which layout to use based on `proto_version` from [[protocol-versioning]] handshake.

### CLOSE payload (download direction: agent → host reply to GET)

**v0:**
```
crc32(4 bytes, big-endian)
```

**v1:**
```
crc32(4 BE) fat_time(2 LE) fat_date(2 LE)
```

Host applies the mtime via `os.utime` if `len(payload) >= 8`.

### VERSION ACK payload

```
version_byte(1)    # currently 0x01
```

A v0 agent returns empty ACK (falls through to default handler). A v1 agent explicitly handles T_VERSION and replies `ACK + [0x01]`.

## Sequence numbers

`seq` starts at 0 per session and increments modulo 256. Each request uses the current seq; ACK/NAK echo the same seq. The agent uses `v_seq` in BSS to track. On seq mismatch the host raises `OSError`.

## Stop-and-wait

Only one outstanding packet at a time. Host sends, waits for ACK/NAK, resends on NAK or timeout. Retries configurable in host.py (default 3).

## Whole-file integrity

CRC-32 accumulated over all DATA payloads and checked in the CLOSE packet (`crc32`, big-endian, 4 bytes at offset 0). Per-packet CRC-16 catches single-packet corruption; CRC-32 catches reordering or missing chunks.

## Backward compatibility

Types 1–9 byte layouts are frozen. Type 10–15 added in the "v2 ops" batch. Type 16 (VERSION) added with v1. New hosts work with old agents at protocol v0 (no timestamps, no version query reply needed). See [[protocol-versioning]].
