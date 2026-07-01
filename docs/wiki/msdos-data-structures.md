---
title: "MS-DOS v4.0 Core Data Structures"
type: code-map
sources:
  - MS-DOS/v4.0/src/INC/DPB.INC
  - MS-DOS/v4.0/src/INC/BPB.INC
  - MS-DOS/v4.0/src/INC/DIRENT.INC
  - MS-DOS/v4.0/src/INC/EXE.INC
  - MS-DOS/v4.0/src/INC/BUFFER.INC
  - MS-DOS/v4.0/src/INC/SYSVAR.INC
related:
  - "[[msdos-v4-architecture]]"
  - "[[msdos-kernel-modules]]"
  - "[[msdos-fat16-format]]"
created: 2026-06-26
updated: 2026-06-26
confidence: high
---

# MS-DOS v4.0 Core Data Structures

The MS-DOS kernel uses a set of interconnected data structures to manage drives, files, memory, and processes. These structures are defined in the `INC/` header files and referenced throughout the `DOS/` kernel source. This page documents each structure's layout, fields, and role in the system.

## DPB — Drive Parameter Block

**Source:** `INC/DPB.INC:7-29`
**Size:** 27 bytes (`DPBSIZ`)
**Role:** Runtime per-drive metadata. One DPB exists per logical drive, chained via `dpb_next_dpb`. The kernel uses DPBs for all FAT operations, cluster arithmetic, and buffer cache lookups.

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| +00 | `dpb_drive` | DB | Logical drive number (A=0, B=1, ...) |
| +01 | `dpb_UNIT` | DB | Driver unit number |
| +02 | `dpb_sector_size` | DW | Physical sector size in bytes (typically 512) |
| +04 | `dpb_cluster_mask` | DB | Sectors per cluster minus 1 (e.g., 1 for 2 sectors/cluster) |
| +05 | `dpb_cluster_shift` | DB | Log2 of sectors per cluster (for shift-based arithmetic) |
| +06 | `dpb_first_FAT` | DW | Starting sector of first FAT |
| +08 | `dpb_FAT_count` | DB | Number of FAT copies (typically 2) |
| +09 | `dpb_root_entries` | DW | Number of root directory entries (typically 512) |
| +0B | `dpb_first_sector` | DW | First sector of data region (first cluster) |
| +0D | `dpb_max_cluster` | DW | Number of clusters + 1; **threshold for FAT12/FAT16**: >= 4096 means FAT16 |
| +0F | `dpb_FAT_size` | DW | Sectors occupied by one FAT |
| +11 | `dpb_dir_sector` | DW | Starting sector of root directory |
| +13 | `dpb_driver_addr` | DD | Pointer to disk driver |
| +17 | `dpb_media` | DB | Media descriptor byte (see FAT16 page) |
| +18 | `dpb_first_access` | DB | Initialized to -1 to force media check on first use |
| +19 | `dpb_next_dpb` | DD | Pointer to next DPB in chain |
| +1D | `dpb_next_free` | DW | Cluster number of last allocated cluster (free space hint) |
| +1F | `dpb_free_cnt` | DW | Count of free clusters, -1 if unknown |

**Key usage:** `dpb_max_cluster` is the FAT12/FAT16 discriminator — `FAT.ASM:80-94` checks if this value is >= 4096 to select 16-bit vs 12-bit FAT algorithms. The `dpb_cluster_mask` and `dpb_cluster_shift` fields enable fast cluster-to-sector conversion without division.

## BPB — BIOS Parameter Block

**Source:** `INC/BPB.INC:10-19`
**Size:** 13 bytes
**Role:** On-disk boot sector structure. The BPB is read from sector 0 during boot to initialize the DPB. It describes the physical and logical geometry of the disk.

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| +00 | `BPSECSZ` | DW | Bytes per physical sector |
| +02 | `BPCLUS` | DB | Sectors per allocation unit (cluster) |
| +03 | `BPRES` | DW | Number of reserved sectors (boot sector + space) |
| +05 | `BPFTCNT` | DB | Number of FAT copies |
| +06 | `BPDRCNT` | DW | Number of root directory entries |
| +08 | `BPSCCNT` | DW | Total number of sectors on disk (0 if > 32MB) |
| +0A | `BPMEDIA` | DB | Media descriptor byte |
| +0B | `BPFTSEC` | DW | Sectors per FAT |

## A_BPB — Extended BIOS Parameter Block

**Source:** `INC/BPB.INC:21-37`
**Size:** 28 bytes
**Role:** Extended BPB for disks larger than 32MB. Adds CHS geometry, hidden sectors, and a 32-bit total sector count. Used by MS-DOS 4.0+ for larger drives.

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| +00 | `BPB_BYTESPERSECTOR` | DW | Bytes per sector |
| +02 | `BPB_SECTORSPERCLUSTER` | DB | Sectors per cluster |
| +03 | `BPB_RESERVEDSECTORS` | DW | Reserved sectors |
| +05 | `BPB_NUMBEROFFATS` | DB | Number of FATs |
| +06 | `BPB_ROOTENTRIES` | DW | Root directory entries |
| +08 | `BPB_TOTALSECTORS` | DW | Total sectors (0 if > 32,767) |
| +0A | `BPB_MEDIADESCRIPTOR` | DB | Media descriptor |
| +0B | `BPB_SECTORSPERFAT` | DW | Sectors per FAT |
| +0D | `BPB_SECTORSPERTRACK` | DW | Sectors per track (CHS geometry) |
| +0F | `BPB_HEADS` | DW | Number of heads (CHS geometry) |
| +11 | `BPB_HIDDENSECTORS` | DW | Hidden sectors before partition |
| +13 | *(reserved)* | DW | Reserved |
| +15 | `BPB_BIGTOTALSECTORS` | DW | Big total sectors (32-bit count, high word) |
| +17 | *(reserved)* | DW | Reserved |
| +19 | *(reserved)* | DB×6 | Reserved padding |

**Note:** `BPB_TOTALSECTORS` and `BPB_BIGTOTALSECTORS` together form a 32-bit sector count, enabling support for disks up to ~2GB.

## Directory Entry

**Source:** `INC/DIRENT.INC:28-61`
**Size:** 32 bytes
**Role:** On-disk file metadata. Root directory entries are stored contiguously after the FAT(s); subdirectory entries are stored in data clusters. A directory is simply a file containing directory entries.

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| +00 | `dir_name` | DB×11 | 8.3 filename (8 chars name + 3 chars extension, padded with 0x20) |
| +0B | `dir_attr` | DB | Attribute bits |
| +0C | `dir_codepg` | DW | Code page (DOS 4.0 addition) |
| +0E | `dir_extcluster` | DW | Extended attribute starting cluster (DOS 4.0) |
| +10 | `dir_attr2` | DB | Reserved |
| +11 | `dir_pad` | DB×5 | Reserved for expansion |
| +16 | `dir_time` | DW | Time of last write |
| +18 | `dir_date` | DW | Date of last write |
| +1A | `dir_first` | DW | First allocation cluster |
| +1C | `dir_size_l` | DW | Low 16 bits of file size |
| +1E | `dir_size_h` | DW | High 16 bits of file size |

### Attribute Bits (`dir_attr`)

| Bit | Value | Constant | Meaning |
|-----|-------|----------|---------|
| 0 | `01h` | `attr_read_only` | Read-only file |
| 1 | `02h` | `attr_hidden` | Hidden file |
| 2 | `04h` | `attr_system` | System file |
| 3 | `08h` | `attr_volume_id` | Volume label |
| 4 | `10h` | `attr_directory` | Subdirectory entry |
| 5 | `20h` | `attr_archive` | Archive bit (modified since last backup) |
| 6 | `40h` | `attr_device` | Device entry (never set on disk; used internally by GETPATH) |

### Special Name Values
- First byte = `0xE5`: Deleted/free entry
- First byte = `0x00`: End of directory
- First byte = `0x05`: Displayed as `0xE5` (workaround for E5 as first char)

### Time/Date Encoding
- **Time:** bits 0-4 = seconds/2, bits 5-10 = minutes, bits 11-15 = hours
- **Date:** bits 0-4 = day, bits 5-8 = month, bits 9-15 = year offset from 1980

### Attribute Combinations
| Constant | Value | Usage |
|----------|-------|-------|
| `attr_all` | `16h` | OR of hidden+system+directory (for FINDENTRY search) |
| `attr_ignore` | `61h` | read_only+archive+device (ignored during search) |
| `attr_changeable` | `27h` | Attributes modifiable via CHMOD |

## EXE File Header

**Source:** `INC/EXE.INC:52-71`
**Size:** 28 bytes (+ relocation table)
**Role:** Portable executable format for MS-DOS. The MZ header describes how to load, relocate, and execute the program. Used by the EXEC system call (`DOS/EXEC.ASM`).

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| +00 | `exe_signature` | DW | Must be `5A4Dh` ("MZ" = Mark Zbikowski) |
| +02 | `exe_len_mod_512` | DW | Remaining bytes of file after full 512-byte pages |
| +04 | `exe_pages` | DW | Number of 512-byte pages in file |
| +06 | `exe_rle_count` | DW | Number of relocation table entries |
| +08 | `exe_par_dir` | DW | Paragraphs of header before image |
| +0A | `exe_min_BSS` | DW | Minimum BSS (zero-fill) paragraphs |
| +0C | `exe_max_BSS` | DW | Maximum BSS paragraphs |
| +0E | `exe_SS` | DW | Initial stack segment |
| +10 | `exe_SP` | DW | Initial stack pointer |
| +12 | `exe_chksum` | DW | Checksum (ignored by DOS) |
| +14 | `exe_IP` | DW | Entry point IP |
| +16 | `exe_CS` | DW | Entry point CS |
| +18 | `exe_rle_table` | DW | Byte offset of relocation table |
| +1A | `exe_iov` | DW | Overlay number (0 = root image) |
| +1C | `exe_sym_tab` | DD | Offset of symbol table (debug only) |

**Valid signatures:** `5A4Dh` (standard) and `4D5Ah` (old/reversed, also accepted).

### EXEC Argument Blocks

**Source:** `INC/EXE.INC:16-37`

Three argument block variants for the EXEC syscall (INT 21h AH=4Bh):

| Block | Extra Fields (after standard) | Usage |
|-------|------------------------------|-------|
| `Exec0` | None | Load-only (don't execute) |
| `Exec1` | `SP`, `SS`, `IP`, `CS` | Override entry point and stack |
| `Exec3` | `load_addr`, `reloc_fac` | Load at specific address with relocation factor |

All blocks share: `environ` (environment segment), `com_line` (command line pointer), `5C_FCB` and `6C_FCB` (default FCB slots in PSP).

### Exit Codes

| Code | Constant | Meaning |
|------|----------|---------|
| 0 | `Exit_terminate` | Normal termination |
| 0 | `Exit_abort` | Abort (same code as terminate) |
| 1 | `Exit_Ctrl_C` | Ctrl+C interrupt |
| 2 | `Exit_Hard_Error` | Hard error |
| 3 | `Exit_Keep_process` | Keep process (internal) |

## BUFFINFO — Buffer Cache Entry

**Source:** `INC/BUFFER.INC:9-42`
**Size:** 20 bytes (`BUFINSIZ`)
**Role:** Per-buffer metadata for the disk I/O cache. Buffers are organized in an LRU doubly-linked list and a hash table for fast lookup. DOS 4.0 supports EMS-backed buffers for larger caches.

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| +00 | `buf_next` | DW | Next buffer in LRU list |
| +02 | `buf_prev` | DW | Previous buffer in LRU list |
| +04 | `buf_ID` | DB | Drive number (bit 7=0) or SFT index (bit 7=1); `0FFh` = free |
| +05 | `buf_flags` | DB | Buffer flags (see below) |
| +06 | `buf_sector` | DD | Sector number (bit 7=0) or file offset (bit 7=1) |
| +0A | `buf_wrtcnt` | DB | FAT sector write counter |
| +0B | `buf_wrtcntinc` | DW | FAT sector write interval |
| +0D | `buf_DPB` | DD | Pointer to DPB (bit 7=0) or fill info (bit 7=1) |
| +11 | `buf_fill` | DW | Buffer fill level (bit 7=1) |
| +13 | `buf_reserved` | DB | Padding for DWORD alignment (386) |

### Buffer Flags (`buf_flags`)

| Bit | Mask | Constant | Meaning |
|-----|------|----------|---------|
| 7 | `10000000B` | `buf_isnet` | Remote/network buffer |
| 6 | `01000000B` | `buf_dirty` | Buffer has unsaved changes |
| 5 | `00100000B` | `buf_visit` | Search visit flag |
| 4 | `00010000B` | `buf_snbuf` | Search bit (SFT buffer) |
| 3 | `00001000B` | `buf_isDATA` | Data buffer |
| 2 | `00000100B` | `buf_isDIR` | Directory buffer |
| 1 | `00000010B` | `buf_isFAT` | FAT buffer |

## Buffer Hash Entry

**Source:** `INC/BUFFER.INC:64-72`
**Role:** Hash table bucket for buffer cache lookups. DOS 4.0 uses hashing instead of linear search for O(1) buffer lookup.

| Field | Size | Default | Description |
|-------|------|---------|-------------|
| `EMS_PAGE_NUM` | DW | -1 | EMS logical page number |
| `BUFFER_BUCKET` | DD | 0 | Pointer to buffer chain |
| `DIRTY_COUNT` | DB | 0 | Dirty buffers in this bucket |
| `BUFFER_RESERVED` | DB | 0 | Reserved |

**Limits:** Max 15 buffers per bucket, max 2 buckets per 16KB EMS page.

## SysInitVars — System Initialization Variables

**Source:** `INC/SYSVAR.INC:4-29`
**Role:** Global system state, initialized during boot. Points to all major kernel data structures. Extended version (`SysInitVars_Ext`) adds country/codepage info.

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| +00 | `SYSI_DPB` | DD | Pointer to DPB chain head |
| +04 | `SYSI_SFT` | DD | Pointer to SFT (System File Table) chain |
| +08 | `SYSI_CLOCK` | DD | CLOCK device pointer |
| +0C | `SYSI_CON` | DD | CON (console) device pointer |
| +10 | `SYSI_MAXSEC` | DW | Maximum sector size |
| +12 | `SYSI_BUF` | DD | Pointer to hash table init vars |
| +16 | `SYSI_CDS` | DD | CDS (Current Directory Structure) list |
| +1A | `SYSI_FCB` | DD | FCB (File Control Block) chain |
| +1E | `SYSI_Keep` | DW | FCB keep count |
| +20 | `SYSI_NUMIO` | DB | Number of block devices |
| +21 | `SYSI_NCDS` | DB | Number of CDS structures |
| +22 | `SYSI_DEV` | DD | Device list head |
| +26 | `SYSI_ATTR` | DW | Null device attribute word |
| +28 | `SYSI_STRAT` | DW | Null device strategy entry |
| +2A | `SYSI_INTER` | DW | Null device interrupt entry |
| +2C | `SYSI_NAME` | DB×8 | Null device name |
| +34 | `SYSI_SPLICE` | DB | Splice operation flag |
| +35 | `SYSI_IBMDOS_SIZE` | DW | DOS size in paragraphs |
| +37 | `SYSI_IFS_DOSCALL@` | DD | IFS DOS service entry |
| +3B | `SYSI_IFS` | DD | IFS header chain |
| +3F | `SYSI_BUFFERS` | DW×2 | BUFFERS= values (m, n) |
| +43 | `SYSI_BOOT_DRIVE` | DB | Boot drive (A=1, B=2, ...) |
| +44 | `SYSI_DWMOVE` | DB | 386 machine flag |
| +45 | `SYSI_EXT_MEM` | DW | Extended memory size in KB |

### SysInitVars_Ext (Extended)

| Field | Size | Description |
|-------|------|-------------|
| `SYSI_InitVars` | DD | Pointer to base SysInitVars |
| `SYSI_Country_Tab` | DD | Country/codepage info table |

## Buffinfo — Buffer Manager State

**Source:** `INC/SYSVAR.INC:41-69`
**Role:** Global buffer cache manager state, pointed to by `SYSI_BUF`. Manages hash table, secondary cache, and EMS integration.

| Field | Size | Default | Description |
|-------|------|---------|-------------|
| `Hash_ptr` | DD | 0 | Pointer to hash table |
| `Hash_count` | DW | 0 | Number of hash entries |
| `Cache_ptr` | DD | 0 | Pointer to secondary cache |
| `Cache_count` | DW | 0 | Secondary cache entry count |
| `EMS_mode` | DB | -1 | EMS mode (-1 = no EMS) |
| `EMS_handle` | DW | 0 | EMS handle for buffers |
| `EMS_PageFrame_Number` | DW | -1 | EMS page frame number |
| `EMS_Seg_Cnt` | DW | 1 | EMS segment count |
| `EMS_Page_Frame` | DW | -1 | EMS page frame segment address |
| `EMS_Map_Buff` | DB×12 | 0 | EMS map buffer |

**Conditional fields** (when `BUFFERFLAG` is set): `EMS_SAFE_FLAG`, `EMS_LAST_PAGE`, `EMS_FIRST_PAGE`, `EMS_NPA640` for 640KB NPA tracking.

## SFT — System File Table

**Source:** Referenced in `DOS/MSCONST.ASM:69`, `DOS/MSINIT.ASM:77`, `DOS/CLOSE.ASM:268`
**Role:** Runtime file table — one entry per open file. The SFT is the kernel's internal file handle table, analogous to Unix's `/proc/*/fd/`. Each entry tracks file state, position, DPB reference, and directory context.

The SFT structure is not defined as a formal `STRUC` in the source. Its fields are accessed via offsets from the base pointer (`sfTabl`). Key fields observed in the source:

| Field | Description |
|-------|-------------|
| `sft_ref_count` | Reference count (decremented on CLOSE; 0 = free) |
| `sft_state` | File state flags |
| `sft_DPB` | Pointer to associated DPB |
| `sft_drive` | Drive number |
| `sft_mode` | Open mode (read/write/read-write) |
| `sft_flags` | File flags |
| `sft_attr` | File attributes |
| `sft_uid` | User ID (network) |
| `sft_pid` | Process ID |
| `sft_size` | File size (32-bit) |
| `sft_position` | Current file position |
| `sft_time` | Last access time |
| `sft_date` | Last access date |
| `sft_name` | 11-byte filename + code page |

The SFT chain is pointed to by `SYSI_SFT` in SysInitVars. Critical section `critSFT` protects SFT allocation.

## CDS — Current Directory Structure

**Source:** Referenced in `INC/SYSVAR.INC:11` (`SYSI_CDS`)
**Role:** Per-drive current directory tracking. One CDS exists per logical drive. The CDS list is pointed to by `SYSI_CDS`; the count is in `SYSI_NCDS`.

The CDS tracks the current working directory for each drive, enabling CHDIR operations without full path resolution. When a process changes drive, the kernel looks up the CDS for that drive to determine the current directory.

## PSP — Program Segment Prefix

**Source:** Documented in `sources/msdos-int21.md`; referenced via `GetCurrentPSP` (INT 21h AH=62h, function 98)
**Role:** 256-byte control block at the base of every process's memory segment. Created during EXEC; contains environment pointer, FCB slots, parent PSP, command tail, and DOS-provided data.

Key PSP offsets:
| Offset | Size | Description |
|--------|------|-------------|
| +000h | 3B | `INT 20h` termination code (`CD 20 00 00`) |
| +004h | 1W | Parent PSP segment |
| +006h | 2W | DOS version number |
| +00Ch | 5W | Pointers to DOS syscall entry points |
| +01Ch | 2W | Far return address for INT 22h (terminate) |
| +01Eh | 2W | Far return address for INT 23h (Ctrl+C) |
| +020h | 2W | Far return address for INT 24h (critical error) |
| +02Ch | 2W | Environment segment pointer |
| +02Fh | 1W | Previous environment segment |
| +031h | 4B | Drive error strategy flags |
| +035h | 1W | DOS version (again) |
| +037h | 1B | Country info flag |
| +03Ch | 2W | Default FCB #1 (slot 1) |
| +04Ch | 2W | Default FCB #2 (slot 2) |
| +05Ch | 32B | Default FCB #1 (legacy) |
| +06Ch | 32B | Default FCB #2 (legacy) |
| +080h | 128B | Command line tail (127 chars + length byte) |

## Structure Relationships

```
SysInitVars
├── SYSI_DPB ──→ DPB chain (one per drive)
│                 ├── dpb_next_dpb ──→ next DPB
│                 └── dpb_driver_addr ──→ disk driver
├── SYSI_SFT ──→ SFT chain (one per open file)
│                 └── sft_DPB ──→ owning DPB
├── SYSI_CDS ──→ CDS list (one per drive)
├── SYSI_DEV ──→ device chain (ANSI.SYS, SMARTDRV, etc.)
├── SYSI_BUF ──→ Buffinfo
│                 ├── Hash_ptr ──→ BUFFER_HASH_ENTRY table
│                 └── EMS integration
└── SYSI_IFS ──→ IFS header chain (network/extended FS)
```

**Data flow:** A file open creates an SFT entry → SFT references a DPB → DPB describes the drive's FAT layout → buffer cache (BUFFINFO) caches disk sectors → directory entries (32 bytes each) describe files on disk → EXE headers describe loadable programs.
