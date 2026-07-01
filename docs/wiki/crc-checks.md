---
title: CRC Checks
type: concept
sources:
  - PROTOCOL.md
  - host.py
  - xfercom.asm
related:
  - "[[wire-protocol]]"
  - "[[cobs-framing]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

## Two-level integrity

serial-xfer uses two distinct CRCs for two different failure modes:

| Check | Algorithm | Scope | Purpose |
|-------|-----------|-------|---------|
| Per-packet | CRC-16/CCITT | Header + payload of one packet | Detect bit errors on the wire |
| Whole-file | CRC-32 | All DATA payloads concatenated | Detect truncation, reordering, missing chunks |

## CRC-16/CCITT (per-packet)

- Polynomial: `0x1021` (x^16 + x^12 + x^5 + 1)
- Initial value: `0xFFFF`
- Input reflection: no
- Output XOR: none (same as XMODEM CRC, sometimes called "CRC-CCITT false start")
- Sent as 2 bytes appended after the payload, **inside** the COBS frame.

On the agent side (`xfercom.asm`), the CRC-16 routine uses a precomputed 256-entry word table (512 bytes). The table is the largest single data structure in the binary.

On the host side (`host.py`), `crc16(data)` is a pure-Python table lookup.

**Failure action:** if the receiver's computed CRC doesn't match, it sends NAK and the sender retransmits.

### Why CRC-16 not checksum?

A simple arithmetic checksum misses transposition errors (0x01 0x02 ↔ 0x02 0x01 = same sum). CRC-16 catches those. On noisy RS-232 at 115 kbaud, multi-bit burst errors are common; CRC-16 catches all 1-bit and 2-bit errors in any position, and most burst errors up to 16 bits.

## CRC-32 (whole-file)

- Algorithm: standard ISO 3309 CRC-32 (same as gzip, PNG, Ethernet)
- Polynomial: `0xEDB88320` (reflected)
- Initial value: `0xFFFFFFFF`, final XOR `0xFFFFFFFF`
- Transmitted as **4 bytes, big-endian**, in the CLOSE packet payload (bytes 0–3).

On the agent, `crc32_update` runs on each DATA chunk as it's written to disk; the running CRC is in `v_wcrc` (dword in BSS). The host computes its own running CRC over what it sent, and compares in CLOSE.

**Failure action:** agent sends NAK on CRC-32 mismatch; host retries the whole file upload. Download CRC-32 is checked host-side; mismatch → retry the download.

### Why CRC-32 for whole-file?

CRC-16 alone on 512-byte chunks can't detect that two packets arrived in the wrong order, or that a chunk was duplicated. CRC-32 over the whole concatenated content catches those cases with negligible collision probability (1 in 4 billion).

## Implementation in xfercom.asm

The CRC-16 table is assembled as `dw` entries in the `.text` section (not BSS) — it is initialized data, so it takes space in XFER.COM. This is the main fixed overhead beyond the code itself.

CRC-32 uses a smaller (256-entry, byte-width) table, also assembled inline. Together the two tables account for roughly 600 bytes of the ~2636-byte total.

## Why not MD5/SHA?

MD5/SHA would require 1–4 KB of code on the agent side. With a 3 KB total budget for XFER.COM and an 8086 CPU with no multiply-immediate, CRC-32 is the strongest checksum that fits.
