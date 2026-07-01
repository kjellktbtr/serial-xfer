---
title: COBS Framing
type: concept
sources:
  - PROTOCOL.md
  - host.py
  - xfercom.asm
related:
  - "[[wire-protocol]]"
  - "[[crc-checks]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

## What is COBS?

**Consistent Overhead Byte Stuffing** (COBS) is a framing scheme that eliminates `0x00` from the interior of a message, reserving it as a frame delimiter. This makes packet boundaries unambiguous on a byte-stream serial link with no other framing.

Reference: Cheshire & Baker, "Consistent Overhead Byte Stuffing," IEEE/ACM ToN 1999.

## Why COBS (vs. alternatives)?

| Scheme | Overhead | Framing | Notes |
|--------|----------|---------|-------|
| COBS | ≤1 byte per 254 | 0x00 delimiter | Deterministic overhead |
| SLIP | Variable | 0xC0 delimiter | Escaping doubles worst-case |
| Length-prefixed | 0 | Length field | Requires reliable channel |
| HDLC | Variable | Flag bytes | Escape-based; more complex |

COBS overhead is at most `ceil(n/254)` bytes for an n-byte payload — essentially free for packets ≤254 bytes (one overhead byte). For the 512-byte max data chunks used here, worst-case overhead is 3 bytes.

## How it works

### Encoding

Split the data into chunks of up to 254 bytes, separated wherever a `0x00` byte would appear. Each chunk is prefixed by a **distance-to-next-zero-or-end** byte (1–255):

1. Scan forward to find the next `0x00` or end-of-data.
2. Emit the distance (number of non-zero bytes + 1) as the overhead byte.
3. Emit the non-zero bytes.
4. Repeat.
5. Terminate with the delimiter `0x00`.

The overhead byte for a chunk of 254 non-zero bytes is `0xFF`.

### Decoding

1. Read bytes until `0x00` (the delimiter).
2. The first byte is the distance `d` to the next "block boundary."
3. Copy `d-1` bytes as payload.
4. If `d < 0xFF`, emit a `0x00` (the original zero byte that was replaced).
5. Jump to position `d`, repeat.

### Example

Input: `[0x11, 0x00, 0x22]`
→ `[0x02, 0x11, 0x02, 0x22, 0x00]`

Input: `[0x11, 0x22, 0x33]` (no zeros)
→ `[0x04, 0x11, 0x22, 0x33, 0x00]`

## Frame structure in serial-xfer

```
[COBS-encoded data] 0x00
```

The data passed to COBS is `type(1) + seq(1) + payload(0..512) + crc16(2)`.

After COBS encoding and before the `0x00` delimiter:
- No `0x00` bytes appear inside the frame → easy to resync after errors.
- The `0x00` delimiter also serves as an idle marker: if the line goes quiet (e.g., the DOS agent is computing), the host waits for the next `0x00`.

## Implementation

### Python (`host.py`)

```python
def cobs_encode(data: bytes) -> bytes:
    ...  # builds overhead bytes, no zeros in output

def cobs_decode(data: bytes) -> bytes:
    ...  # reconstructs original with zeros restored
```

### Assembly (`xfercom.asm`)

`encode_cobs` and `decode_cobs` subroutines work in-place on the `tx` and `rxf` buffers respectively. Both are 8086-clean (no 186+ instructions). SI/DI register pair walks input; separate output pointer tracks overhead byte position.

## Resync on error

If a CRC-16 check fails, the agent sends NAK and discards the frame. Because `0x00` is the delimiter, the receiver always knows where a frame ends, even if it arrived during a partial frame — the next `0x00` unambiguously starts a new search. This makes error recovery straightforward without any additional out-of-band signalling.
