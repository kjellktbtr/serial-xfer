---
title: Protocol Versioning (T_VERSION Handshake)
type: decision
sources:
  - PROTOCOL.md
  - host.py
  - xfercom.asm
related:
  - "[[wire-protocol]]"
  - "[[dos-agent]]"
  - "[[host-tool]]"
  - "[[dos-datetime-format]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

## Decision

Capability negotiation is done via a **T_VERSION packet** (type 16) sent by the host once at session start. The agent replies with its protocol version as a 1-byte ACK payload. All new features are gated on the negotiated version.

**Current versions:**
- `0` — baseline (original protocol, types 1–15; no timestamps)
- `1` — adds date+time in ENTRY and CLOSE packets

## Rationale

### Problem

Two improvements required the wire format to change:
1. ENTRY packets needed 4 extra bytes (FAT time + date) between size and name.
2. CLOSE packets needed 4 extra bytes (FAT time + date) after the CRC-32.

Adding these unconditionally would break old `XFER.COM` binaries still in use on DOS machines — a v0 agent parsing a v1 CLOSE would get confused by the extra bytes.

### Why T_VERSION, not other approaches?

| Option | Pros | Cons |
|--------|------|------|
| **T_VERSION handshake (chosen)** | Zero overhead when v0; clean capability gate | One extra round-trip at session start |
| Hard protocol break (new type numbers for ENTRY/CLOSE) | No negotiation needed | Old agents break immediately |
| Feature flags in OPEN | Compact | Ties feature detection to upload; doesn't help download/list |
| Separate negotiation type with bitmask | Extensible | More code on 8086 agent |

The T_VERSION approach allows a **single new binary** to be deployed to new machines while the host tool works with old binaries without any configuration.

### Why type 16 specifically?

Types 1–9 are the "frozen base" (upload, download, list, misc). Types 10–15 were added as the "v2 ops" batch (del, rmdir, rename, pread, pwrite, raw). Type 16 is next in sequence — it fits naturally without any renumbering and avoids colliding with NAK (127).

### Backward compatibility guarantee

A v0 agent never has a handler for type 16. It falls through the dispatch chain to the default ACK handler (`xfercom.asm` `.crc_ok` fall-through), which sends an **empty ACK** (0 payload bytes). The host reads 0 payload bytes → `rdata[0]` would raise `IndexError` → the `if rdata else 0` guard maps this to version 0. Connection-level timeout (if the old agent hangs on an unknown type) is also caught and mapped to version 0.

```python
def query_version(self) -> int:
    try:
        rdata = self.xact(T_VERSION)
        self.proto_version = rdata[0] if rdata else 0
    except OSError:
        self.proto_version = 0
    return self.proto_version
```

## What version gates

| Feature | Minimum version |
|---------|----------------|
| FAT date+time in ENTRY | 1 |
| FAT date+time in CLOSE (download) | 1 |
| FAT date+time in CLOSE (upload) | 1 |
| `st_mtime` in FUSE mount | 1 (falls back to "now" if v0) |

## Future versioning

If a future feature requires further wire changes, bump the version byte in `.h_version` (`mov byte [eb], 2`) and add `if self.proto_version >= 2:` guards. The handshake itself never changes — type 16 always queries version.

For features that are completely new packet types (not extensions of existing payloads), a new type number can be added without bumping the version — the host simply checks for ACK vs. NAK.

## Test coverage

`test_com.py::test_version_and_timestamps` verifies:
1. `link.query_version()` returns 1.
2. ENTRY mtime is parsed and non-None.
3. Download applies `os.utime` with the correct mtime.
4. Upload causes `do_setftime` to be called (verified via `_FakeDos.ftimes`).
