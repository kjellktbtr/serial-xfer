---
title: DOS/FAT Date and Time Format
type: concept
sources:
  - PROTOCOL.md
  - host.py
  - xfercom.asm
related:
  - "[[wire-protocol]]"
  - "[[dos-agent]]"
  - "[[host-tool]]"
  - "[[protocol-versioning]]"
created: 2026-07-01
updated: 2026-07-01
confidence: high
---

## Overview

DOS and FAT filesystems store file modification dates and times as two 16-bit packed integers — the same integers that INT 21h AH=57h reads and writes. The serial-xfer protocol transmits these integers directly over the wire (little-endian), with no conversion on the agent side.

## Packed date (16-bit)

```
Bit 15..9  Year offset from 1980   (0–127 → 1980–2107)
Bit 8..5   Month                   (1–12)
Bit 4..0   Day                     (1–31)
```

Formula: `fat_date = (year - 1980) << 9 | month << 5 | day`

Year 0 → 1980. Year 127 → 2107 (the FAT year rollover limit).

## Packed time (16-bit)

```
Bit 15..11  Hours    (0–23)
Bit 10..5   Minutes  (0–59)
Bit 4..0    Seconds/2  (0–29 → 0–58 seconds)
```

Formula: `fat_time = hours << 11 | minutes << 5 | (seconds // 2)`

**2-second resolution:** the seconds field is halved. 13:45:30 and 13:45:31 both encode as the same value. This is a FAT limitation, not a protocol choice.

## INT 21h AH=57h

The DOS get/set file date+time interrupt:
- `AH=57h, AL=00h, BX=handle` → `CX=time, DX=date`
- `AH=57h, AL=01h, BX=handle, CX=time, DX=date` → sets date+time

The file handle must be open for this to work. The agent calls `do_getftime` **before** closing the file in `serve_get`, and `do_setftime` **before** `do_close` in `.h_close`.

## DTA layout

The Disk Transfer Area (DTA) returned by `find_first`/`find_next` (INT 21h 4Eh/4Fh) holds the FAT date and time at fixed offsets:

```
DTA+21  ATTR (byte)
DTA+22  TIME (word, little-endian)
DTA+24  DATE (word, little-endian)
DTA+26  SIZE (dword, little-endian)
DTA+30  NAME (13 bytes, ASCIIZ)
```

`xfercom.asm` defines `DTA_TIME equ 22` and `DTA_DATE equ 24`. `serve_list` reads these directly from `dta` and copies them into the ENTRY packet payload.

## Wire encoding

Both fields are transmitted as little-endian 16-bit integers, matching the native byte order of all 8086/x86 machines:
- Bytes 5–6 of ENTRY payload: FAT time (low byte first)
- Bytes 7–8 of ENTRY payload: FAT date (low byte first)
- Bytes 4–5 of CLOSE reply: FAT time (low byte first)
- Bytes 6–7 of CLOSE reply: FAT date (low byte first)

## Python helpers (`host.py`)

```python
def epoch_to_fat(mtime: float) -> tuple[int, int]:
    """Unix timestamp → (fat_date, fat_time)"""
    dt = datetime.datetime.fromtimestamp(mtime)
    fat_date = (dt.year - 1980) << 9 | dt.month << 5 | dt.day
    fat_time = dt.hour << 11 | dt.minute << 5 | dt.second // 2
    return fat_date, fat_time

def fat_to_epoch(fat_date: int, fat_time: int) -> float | None:
    """(fat_date, fat_time) → Unix timestamp, or None if both zero."""
    if fat_date == 0 and fat_time == 0:
        return None
    year  = 1980 + (fat_date >> 9)
    month = (fat_date >> 5) & 0x0F
    day   = fat_date & 0x1F
    hour  = fat_time >> 11
    minute = (fat_time >> 5) & 0x3F
    second = (fat_time & 0x1F) * 2
    return datetime.datetime(year, month, day, hour, minute, second).timestamp()
```

**Local time:** DOS timestamps are local time (no timezone). `datetime.fromtimestamp()` and `datetime(...).timestamp()` both operate in local time, so the round-trip is consistent as long as the host PC is in the same timezone as when the file was last modified on DOS. For vintage machines this is typically acceptable.

## Sentinel value

`fat_date=0, fat_time=0` is used as "no timestamp" — `fat_to_epoch` returns `None` for this case. A real FAT timestamp of 0 would mean 1980-00-00 00:00:00, which is an invalid date. DOS itself never generates this value for real files.
