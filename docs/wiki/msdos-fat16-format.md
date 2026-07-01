---
title: "FAT16 File System Format"
type: concept
sources:
  - MS-DOS/v4.0/src/DOS/FAT.ASM
  - MS-DOS/v4.0/src/INC/DPB.INC
  - MS-DOS/v4.0/src/INC/BPB.INC
  - MS-DOS/v4.0/src/INC/DIRENT.INC
related:
  - "[[msdos-v4-architecture]]"
  - "[[msdos-data-structures]]"
created: 2026-06-26
updated: 2026-06-26
confidence: high
---

# FAT16 File System Format

The File Allocation Table (FAT) file system is the core storage format of MS-DOS. The source code in `FAT.ASM` and the data structure headers document both **FAT12** (disks < 16MB) and **FAT16** (disks >= 16MB) variants. The distinction is determined at runtime by `dpb_max_cluster`: if >= 4096, the drive uses 16-bit FAT entries.

## Disk Layout

```
+------------------+----+------------------+------------------+------------------+
| Boot Sector      | FAT1 |    FAT2         | Root Directory   | Data Region      |
| (BPB + code)     |    | (optional copy)  | (fixed size)     | (clusters)       |
+------------------+----+------------------+------------------+------------------+
```

### Sector Order

1. **Reserved sectors** (usually 1): Boot sector containing BPB
2. **FAT1**: First copy of the File Allocation Table
3. **FAT2**: Second copy (if `dpb_FAT_count` = 2)
4. **Root Directory**: Fixed-size directory area (max entries from BPB)
5. **Data Region**: Cluster-aligned file data

## Boot Sector / BPB (BIOS Parameter Block)

Defined in `BPB.INC:10-19`. The BPB lives in the boot sector and describes the physical layout of the disk.

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| +00h | `BPSECSZ` | WORD | Physical sector size in bytes (typically 512) |
| +02h | `BPCLUS` | BYTE | Sectors per cluster (power of 2: 1, 2, 4, 8, 16, 32, 64) |
| +03h | `BPRES` | WORD | Reserved sectors (boot sector count, usually 1) |
| +05h | `BPFTCNT` | BYTE | Number of FAT copies (typically 2) |
| +06h | `BPDRCNT` | WORD | Number of root directory entries (typically 512, i.e., 16KB) |
| +08h | `BPSCCNT` | WORD | Total sectors on disk (0 = unknown, used for <32MB) |
| +0Ah | `BPMEDIA` | BYTE | Media descriptor (F8h=floppy, F0h=fixed, F9h=removable HDD) |
| +0Bh | `BPFTSEC` | WORD | Sectors per FAT |

### Extended BPB (`A_BPB` in `BPB.INC:21-37`)

For larger disks, the extended BPB adds:

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| +00h | `BPB_BYTESPERSECTOR` | WORD | Sector size |
| +02h | `BPB_SECTORSPERCLUSTER` | BYTE | Sectors per cluster |
| +03h | `BPB_RESERVEDSECTORS` | WORD | Reserved sectors |
| +05h | `BPB_NUMBEROFFATS` | BYTE | FAT count |
| +06h | `BPB_ROOTENTRIES` | WORD | Root directory entries |
| +08h | `BPB_TOTALSECTORS` | WORD | Total sectors (small disks) |
| +0Ah | `BPB_MEDIADESCRIPTOR` | BYTE | Media type |
| +0Bh | `BPB_SECTORSPERFAT` | WORD | Sectors per FAT (small disks) |
| +0Dh | `BPB_SECTORSPERTRACK` | WORD | Sectors per track (geometry) |
| +0Fh | `BPB_HEADS` | WORD | Number of heads |
| +11h | `BPB_HIDDENSECTORS` | DWORD | Hidden sectors (partition offset) |
| +19h | `BPB_BIGTOTALSECTORS` | DWORD | Total sectors (>32MB disks) |

## FAT Table Structure

The FAT is an array of entries, one per cluster. Entry values indicate cluster chain status.

### FAT12 vs FAT16 Detection

From `FAT.ASM:80-94` (`IsEof`):
- If `dpb_max_cluster` < 4096 → **FAT12** (12-bit entries, 3 packed per 6 bytes)
- If `dpb_max_cluster` >= 4096 → **FAT16** (16-bit entries, 2 bytes each)

### EOF Markers

| FAT Type | EOF Range | Meaning |
|----------|-----------|---------|
| FAT12 | `0FF0h` – `0FFFh` | Last cluster in chain |
| FAT16 | `0FFF0h` – `0FFFFh` | Last cluster in chain |
| Either | `0000h` | Free cluster |
| Either | `0001h` | Reserved (FAT entry 1 is media ID) |
| FAT16 | `0FFF8h` – `0FFFEh` | Bad cluster marker |

### FAT Entry Packing (FAT12)

From `FAT.ASM:97-155` (`UNPACK`):

FAT12 entries are 12 bits each, packed 3-per-6-bytes:
```
Byte 0-1: Cluster N (low 16 bits, use low 12)
Byte 1-2: Cluster N+1 (high 4 + low 8, use high 12)
Byte 2-3: Cluster N+2 (low 16 bits, use low 12)
```

**UNPACK algorithm** (`FAT.ASM:108-155`):
1. Call `MAPCLUSTER` to get pointer to FAT entry in buffer
2. If `DI` (entry value) is nonzero → shift right 4 bits (`High12`)
3. AND with `0FFFh` to extract 12-bit value
4. Return in `DI`

**PACK algorithm** (`FAT.ASM:169-243`):
1. Call `MAPCLUSTER` to get buffer pointer
2. If byte-aligned (even cluster): clear low bits, OR in new value
3. If nibble-aligned (odd cluster): shift new value left 4, preserve low 4 bits of original
4. Mark buffer dirty via `buf_dirty` flag

## Cluster Chain Traversal

### MAPCLUSTER (`FAT.ASM:261-363`)

Computes the FAT sector and offset for a given cluster number:

**FAT12**: `byte_offset = 1.5 * cluster` (i.e., `cluster + cluster/2`)
**FAT16**: `byte_offset = 2 * cluster`

**Fast path for 512-byte sectors** (`FAT.ASM:279-301`):
```
; Instead of DIV (158 cycles), use shift+AND for 512-byte sectors (20 cycles):
AND DX, 511        ; remainder = offset within sector
SHR AH, 1          ; quotient high byte
```

### Cluster Numbering

- Cluster 0: Reserved (FAT entry contains media ID)
- Cluster 1: Reserved
- Cluster 2+: First usable data cluster
- Root directory starts at cluster 2 (before data region)

## Directory Entry Format

Defined in `DIRENT.INC:28-61`. Each entry is 32 bytes.

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| +00h | `dir_name` | 11 bytes | 8.3 filename (padded with 0x20) |
| +0Bh | `dir_attr` | 1 byte | Attribute bits |
| +0Ch | `dir_codepg` | 2 bytes | Code page (DOS 4.0 addition) |
| +0Eh | `dir_extcluster` | 2 bytes | Extended attribute cluster (DOS 4.0) |
| +10h | `dir_attr2` | 1 byte | Reserved |
| +11h | `dir_pad` | 5 bytes | Reserved for expansion |
| +16h | `dir_time` | 2 bytes | Last write time |
| +18h | `dir_date` | 2 bytes | Last write date |
| +1Ah | `dir_first` | 2 bytes | First cluster number |
| +1Ch | `dir_size_l` | 2 bytes | File size (low 16 bits) |
| +1Eh | `dir_size_h` | 2 bytes | File size (high 16 bits) |

### Special First-Byte Values

- `0xE5` — Deleted entry (overwritten file, slot reusable)
- `0x00` — End of directory (no more entries)
- `0x05` — Displayed as `0xE5` in name byte 1 (workaround for E5 deletion marker)

### Attribute Bits (`dir_attr`)

| Bit | Value | Name | Description |
|-----|-------|------|-------------|
| 0 | `01h` | Read-only | File cannot be modified |
| 1 | `02h` | Hidden | Not shown in normal DIR |
| 2 | `04h` | System | System file |
| 3 | `08h` | Volume ID | Volume label entry |
| 4 | `10h` | Directory | This entry is a subdirectory |
| 5 | `20h` | Archive | Set on modify, cleared by BACKUP |
| 6 | `40h` | Device | **Never set on disk** — used internally by GETPATH for device entries |

### Time/Date Encoding

**Time** (`dir_time`, 16-bit):
- Bits 0-4: Seconds / 2 (0-29, 2-second granularity)
- Bits 5-10: Minutes (0-59)
- Bits 11-15: Hours (0-23)

**Date** (`dir_date`, 16-bit):
- Bits 0-4: Day (1-31)
- Bits 5-8: Month (1-12)
- Bits 9-15: Years since 1980 (0-127, i.e., 1980-2107)

## DPB (Drive Parameter Block) — Runtime Disk State

Defined in `DPB.INC:7-27`. The DPB is built from the BPB at mount time and maintained in memory.

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| +00h | `dpb_drive` | BYTE | Logical drive number (A=0, B=1, ...) |
| +01h | `dpb_unit` | BYTE | Physical drive unit number |
| +02h | `dpb_sector_size` | WORD | Physical sector size (typically 512) |
| +04h | `dpb_cluster_mask` | BYTE | Sectors per cluster minus 1 (for AND masking) |
| +05h | `dpb_cluster_shift` | BYTE | Log2 of sectors per cluster (for shift operations) |
| +06h | `dpb_first_FAT` | WORD | Starting sector of FAT1 |
| +08h | `dpb_FAT_count` | BYTE | Number of FAT copies |
| +09h | `dpb_root_entries` | WORD | Root directory entry count |
| +0Bh | `dpb_first_sector` | WORD | First data sector (start of cluster 2) |
| +0Dh | `dpb_max_cluster` | WORD | Max cluster number + 1 (determines FAT12 vs FAT16) |
| +0Fh | `dpb_FAT_size` | WORD | Sectors per FAT |
| +11h | `dpb_dir_sector` | WORD | Starting sector of root directory |
| +13h | `dpb_driver_addr` | DWORD | Pointer to device driver |
| +17h | `dpb_media` | BYTE | Media descriptor byte |
| +18h | `dpb_first_access` | BYTE | Media check flag (init to -1) |
| +19h | `dpb_next_dpb` | DWORD | Pointer to next DPB in chain |
| +1Dh | `dpb_next_free` | WORD | Last allocated cluster # (free space hint) |
| +1Fh | `dpb_free_cnt` | WORD | Free cluster count (-1 = unknown, needs recount) |

## Buffer Cache

Defined in `BUFFER.INC:9-72`. The disk buffer cache reduces physical disk I/O.

### Buffer Info Structure (`BUFFINFO`)

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| +00h | `buf_next` | WORD | Next buffer in LRU list |
| +02h | `buf_prev` | WORD | Previous buffer in LRU list |
| +04h | `buf_ID` | BYTE | Drive # (bit7=0) or SFT index (bit7=1); `FFh` = free |
| +05h | `buf_flags` | BYTE | Buffer flags (dirty, type, network) |
| +06h | `buf_sector` | DWORD | Sector number |
| +0Ah | `buf_wrtcnt` | BYTE | Write count (FAT sectors) |
| +0Bh | `buf_wrtcntinc` | WORD | Write interval |
| +0Dh | `buf_DPB` | DWORD | Pointer to DPB |
| +11h | `buf_fill` | WORD | Fill level (for remote buffers) |

### Buffer Flags

| Bit | Mask | Name | Meaning |
|-----|------|------|---------|
| 7 | `80h` | `buf_isnet` | Remote/network buffer |
| 6 | `40h` | `buf_dirty` | Buffer modified, needs writeback |
| 3 | `08h` | `buf_isDATA` | Contains data sector |
| 2 | `04h` | `buf_isDIR` | Contains directory sector |
| 1 | `02h` | `buf_isFAT` | Contains FAT sector |

### Hash Table (`BUFFER_HASH_ENTRY`)

- `EMS_PAGE_NUM`: Logical page for EMS handle
- `BUFFER_BUCKET`: Pointer to buffer chain
- `DIRTY_COUNT`: Number of dirty buffers in bucket
- Max 15 buffers per bucket, 2 buckets per 16KB page

## FAT Read/Write Operations

### FATREAD_SFT / FATREAD_CDS (`FAT.ASM:383-400+`)

Called before FAT operations to:
1. Check for disk change (media descriptor comparison)
2. Invalidate affected buffers if disk changed
3. Return DPB pointer in `THISDPB`

### Free Space Tracking

The DPB maintains `dpb_free_cnt` and `dpb_next_free`:
- `dpb_free_cnt = -1` means free space is unknown (needs full FAT scan)
- `dpb_next_free` is a hint for the last allocated cluster (speeds up allocation)
- On FAT error, `dpb_free_cnt` is set to -1 to force recomputation

## Media Descriptor Bytes

| Value | Meaning |
|-------|---------|
| `F8h` | 5.25" DD (double density) floppy |
| `F9h` | 3.5" HD (high density) floppy / removable HDD |
| `F0h` | Fixed disk (hard drive) — "Other" media |
| `F0h` | Also triggers special EOF handling (`0FF0h` accepted as EOF, `FAT.ASM:82-86`) |
