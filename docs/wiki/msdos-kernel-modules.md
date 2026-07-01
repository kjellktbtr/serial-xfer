---
title: "MS-DOS v4.0 Kernel Modules"
type: code-map
sources:
  - MS-DOS/v4.0/src/DOS/DISPATCH.ASM
  - MS-DOS/v4.0/src/DOS/*.ASM
related:
  - "[[msdos-v4-architecture]]"
  - "[[msdos-data-structures]]"
  - "[[msdos-fat16-format]]"
created: 2025-06-26
updated: 2025-06-26
confidence: high
---

# MS-DOS v4.0 Kernel Modules

Detailed file-by-file mapping of the `DOS/` directory. The kernel comprises ~75 `.ASM` files organized into three layers: **system call entry points**, **internal interface modules**, and **low-level modules**.

## System Call Entry Modules

These files implement the top-level INT 21h system calls. Each maps directly to AH codes in the dispatch table (`DISPATCH.ASM`).

| File | System Calls | Description |
|------|-------------|-------------|
| `HANDLE.ASM` | Close (3Eh), Read (3Fh), Write (40h), LSeek (42h), XDup (45h), XDup2 (46h), FileTimes (57h) | Handle-related I/O; top-level calls for file operations |
| `FILE.ASM` | Open (3Dh), Creat (3Ch), ChMod (43h), Unlink (41h), Rename (56h), CreateTemp (5Ah), CreateNew (5Bh) | Pathname-related calls; file creation, deletion, attribute changes |
| `PATH.ASM` | MkDir (39h), RmDir (3Ah), ChDir (3Bh), CurrentDir (47h) | Directory navigation and manipulation |
| `ALLOC.ASM` | $Alloc (48h), $Dealloc (49h), $SetBlock (4Ah), $AllocOper (58h) | Memory arena management; allocation/deallocation with low-level arena routines |
| `SEARCH.ASM` | DirSearchFirst (4Eh), DirSearchNext (4Fh), FindFirst, FindNext, PackName | Directory scan system calls |
| `PROC.ASM` | Exec (4Bh), Exit (4Ch), Abort, Wait (4Dh), KeepProcess (31h) | Process lifecycle: load, execute, terminate, wait |
| `CPMIO.ASM` | StdConInput (01h-0Ch), StdConOutput, StdAuxInput/Output, StdPrinterOutput, RawConIO, StdConInputNoEcho, StdConStringInput/Output, StdConInputStatus, StdConInputFlush | First 12 CP/M-compatible console I/O calls |
| `FCBIO.ASM` | FCBOpen (0Fh), FCBClose (10h), FCBDelete (13h), FCBSeqRead (14h), FCBSeqWrite (15h), FCBCreate (16h), FCBRename (17h), FCBRandomRead (21h), FCBRandomWrite (22h), GetFCBFileLength (23h), GetFCBPosition (24h), FCBRandomReadBlock (27h), FCBRandomWriteBlock (28h) | Legacy FCB (File Control Block) I/O calls |
| `TIME.ASM` | GetDate (2Ah), SetDate (2Bh), GetTime (2Ch), SetTime (2Dh) | Date/time system calls |
| `PARSE.ASM` | Parse_file_descriptor (29h), PathParse | Command line parsing into FCBs |
| `GETSET.ASM` | Get/SetInterruptVector (25h/35h), Get/SetVerify (2Eh/54h), Get/SetDMA (1Ah/2Fh), GetVersion (30h), SetCTRLCTrapping (33h), GetDriveFreespace (36h), CharOper (37h), International (38h), Set/GetDefaultDrive (0Eh/19h), GetExtendedError (59h) | GET/SET family: version, DMA, interrupt vectors, international settings |
| `MISC.ASM` | Sleazefunc, GetDefaultDPB (1Fh), GetDPB (32h), CreateProcessDataBlock (26h), GetINDOSFlag (34h), GetInVars (52h), SetDPB (53h), DupPDB (55h), DiskReset (0Dh) | DPB management, disk reset, process data blocks |

## Internal Interface Modules

These provide the internal API between system call entry points and low-level routines.

| File | Key Routines | Description |
|------|-------------|-------------|
| `CREATE.ASM` | DOS_CREATE, DOS_CREATE_NEW, Set_Mknd_Err | Internal file creation with SFT allocation |
| `OPEN.ASM` | DOS_OPEN, SetBadPathError, Check_Access_AX, Share_Error, Set_SFT_Mode | Internal file open with sharing support |
| `CLOSE.ASM` | DOS_CLOSE, DOS_COMMIT, DOS_CLOSE_GOT_SFT, Free_SFT | Internal SFT close and commit |
| `ABORT.ASM` | DOS_ABORT | Internal abort; closes all handles/FCBs for a process |
| `DUP.ASM` | DOS_DUP | Internal SFT duplication across network |
| `ISEARCH.ASM` | DOS_SEARCH_FIRST, DOS_SEARCH_NEXT, RENAME_NEXT | Internal directory search |
| `DIRCALL.ASM` | DOS_MKDIR, DOS_CHDIR, DOS_RMDIR | Internal directory operations |
| `RENAME.ASM` | DOS_RENAME | Internal file rename |
| `DELETE.ASM` | DOS_DELETE, REN_DEL_Check | Internal file deletion with FastOpen/FastSeek |
| `DISK.ASM` | DOS_READ, DOS_WRITE, SWAPBACK, SWAPCON, DirRead, DskRead, DISKREAD, DISKWRITE, FIRSTCLUSTER, DREAD, DWRITE, DSKWRITE, SETSFT, SETCLUS, AddRec | Low-level disk read/write for local SFT I/O |
| `DINFO.ASM` | DISK_INFO | Internal Get Disk Info (free/total allocation units) |
| `FINFO.ASM` | GET_FILE_INFO, SET_FILE_ATTRIBUTE | Internal get/set file info and attributes |

## Low-Level Modules

Core filesystem, buffer cache, and device driver infrastructure.

| File | Key Routines | Description |
|------|-------------|-------------|
| `FAT.ASM` | IsEOF, UNPACK, PACK, MAPCLUSTER, FATREAD_SFT, FATREAD_CDS, FAT_operation | **FAT12/FAT16 core**: cluster chain traversal, FAT entry packing/unpacking, buffer cache integration |
| `BUF.ASM` | SETVISIT, ScanPlace, PLACEBUF, PLACEHEAD, PointComp, GETBUFFR, GETBUFFRB, FlushBuf, BufWrite, SKIPVISIT | Buffer cache management: placement, flushing, map pages |
| `MKNODE.ASM` | BUILDDIR, SETDOTENT, MakeNode, NEWENTRY, FREEENT, NEWDIR, DOOPEN, RENAME_MAKE | Creates new filesystem nodes; fills SFTs from directory entries |
| `FCB.ASM` | MakeFcb, NameTrans, PATHCHRCMP, GetLet, TESTKANJ, NORMSCAN, CHK, DELIM | FCB parsing: filename analysis and transformation |
| `ROM.ASM` | GET_random_record, GETRRPOS1, GetRRPos, SKPCLP, FNDCLUS, BUFSEC, BUFRD, BUFWRT, NEXTSEC, OPTIMIZE, FIGREC, GETREC, ALLOCATE, RESTFATBYT, RELEASE, RELBLKS, GETEOF | FAT allocation/deallocation, cache reads/writes, FCB computations |
| `DEV.ASM` | IOFUNC, DEVIOCALL, SETREAD, SETWRITE, GOTDPB, DEVIOCALL2, DEV_CLOSE_SFT, DEV_OPEN_SFT | Device driver call infrastructure |
| `DIR.ASM` | SEARCH, SETDIRSRCH, GETPATH, ROOTPATH, StartSrch, MatchAttributes, DEVNAME, Build_device_ent, FindEntry, Srch, NEXTENT, GETENTRY, GETENT, NEXTENTRY, GetPathNoSet, FINDPATH | Path cracking and directory search |
| `CTRLC.ASM` | FATAL, FATAL1, reset_environment, DSKSTATCHK, SPOOLINT, STATCHK, CNTCHAND, DIVOV, RealDivOv, CHARHARD, HardErr | Control-C detection, hard error (INT 24), process termination, divide overflow |

## Variant/Platform Modules

MS-DOS 4.0 supports multiple configurations. These modules provide variant-specific behavior.

| File | Purpose |
|------|---------|
| `DISP.ASM` | Main DOS interrupt dispatcher with version info and copyright |
| `STDDISP.ASM` | Standard dispatch variant |
| `MSDISP.ASM` | MS-DOS specific dispatch variant |
| `MSCODE.ASM` | INT 25h/26h handlers and system call dispatch wrapper |
| `MSINIT.ASM` | DOS initialization routines |
| `MS_TABLE.ASM` | DOS initialization tables and data |
| `MSIOCTL.ASM` | MS-DOS specific IOCTL handling |
| `MSCTRLC.ASM` | MS-DOS specific Control-C handling |
| `MSCPMIO.ASM` | MS-DOS specific CP/M I/O |
| `MSHALO.ASM` | MS-DOS HAL0 (hardware abstraction layer) support |
| `MS_CODE.ASM` | Additional MS-DOS specific code |
| `MSCONST.ASM` | Initialized data and constants for DOS initialization |
| `DOSMES.ASM` | Internationalized message tables |
| `MACRO.ASM` | Pathname macros: AssignOper, FIND_DPB, InitCDS, UserOper, CDS management |
| `MACRO2.ASM` | Pathname macros (part 2): TransFCB, TransPath, Canonicalize, Splice |

## Standard/Network Variant Modules

The `STD`-prefixed files provide standard (non-MS-specific) and network-aware variants.

| File | Purpose |
|------|---------|
| `STDDATA.ASM` | Standard data definitions |
| `STDCTRLC.ASM` | Standard Control-C handling |
| `STDCPMIO.ASM` | Standard CP/M I/O |
| `STDIOCTL.ASM` | Standard IOCTL handling |
| `STDDOSME.ASM` | Standard DOS messages |
| `STDTABLE.ASM` | Standard tables |
| `STDCODE.ASM` | Standard code variants |
| `STDPROC.ASM` | Standard process handling |

## Switch/Configuration Modules

| File | Purpose |
|------|---------|
| `STDSW.ASM` | Standard switch definitions |
| `STDASW.ASM` | Standard alternate switches |
| `HIGHSW.ASM` | High-end switch definitions |
| `MSSW.ASM` | MS-DOS specific switches |
| `CRIT.ASM` | Critical section management (EnterCrit/LeaveCrit macros) |

## Extended Functionality

| File | Purpose |
|------|---------|
| `LOCK.ASM` | File locking: $LockOper, DOS_LOCK, DOS_UNLOCK, Lock_Check, Lock_Violation |
| `SHARE.ASM` | File sharing: Share_Check, Share_Violation |
| `SRVCALL.ASM` | $ServerCall (5Dh) — network server interface |
| `SEGCHECK.ASM` | Segment boundary checking |
| `NSTDOS.ASM` | Non-standard DOS extensions |
| `EXTATTR.ASM` | Extended file attributes support |
| `IFS.ASM` | Installable File System (IFS) driver callbacks |
| `PRINT.ASM` | Print spooler core |
| `DOSPRINT.ASM` | DOS print spooler interface |
| `SHRPRINT.ASM` | Shared print spooler routines |
| `STRIN.ASM` | String input routines |
| `KSTRIN.ASM` | Keyboard string input |
| `UTIL.ASM` | General utility routines |

## Disk I/O Extensions

| File | Purpose |
|------|---------|
| `DISK2.ASM` | Disk utility routines (part 2) |
| `DISK3.ASM` | Low-level disk write routines and write error handling |
| `FCBIO2.ASM` | FCB system calls (part 2): FCB open, create, random/sequential block ops |
| `CPMIO2.ASM` | Device I/O (part 2): console, aux, printer, input status/flush |
| `MISC2.ASM` | String operations, NLS support, fake version, device list |
| `DIR2.ASM` | Directory operations (part 2) |

## Critical Sections

From `DISPATCH.ASM`, system calls are tagged with critical section flags for reentrancy:

| Flag | Name | Scope |
|------|------|-------|
| `1` | critDisk | Buffer cache operations |
| `2` | critDevice | Device driver calls |
| `4` | critMem | Memory allocation |
| `5` | critNet | Network operations |

The macros `EnterCrit` and `LeaveCrit` in `CRIT.ASM` enforce mutual exclusion in multitasking environments.
