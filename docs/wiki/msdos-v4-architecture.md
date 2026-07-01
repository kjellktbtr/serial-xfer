---
title: MS-DOS v4.0 Architecture
type: code-map
sources:
  - MS-DOS/v4.0/src/DOS/DISPATCH.ASM
  - MS-DOS/v4.0/src/BIOS/MSBIO1.ASM
  - MS-DOS/v4.0/src/BOOT/MSBOOT.ASM
  - MS-DOS/v4.0/src/DOS/FAT.ASM
related:
  - "[[msdos-kernel-modules]]"
  - "[[msdos-bios-modules]]"
  - "[[msdos-fat16-format]]"
  - "[[msdos-data-structures]]"
  - "[[msdos-device-drivers]]"
  - "[[msdos-commands]]"
created: 2025-06-26
updated: 2025-06-26
confidence: high
---

# MS-DOS v4.0 Architecture

MS-DOS v4.0 (PC DOS 4.0) er en 16-bit real-mode operativsystem bygget i x86 assembler (MASM). Kildekoden er organisert i tre hovedkomponenter pluss kommandoutiliteter og enhetsdrivere.

## Komponentoversikt

| Komponent | Sti | Filer | Rolle |
|-----------|-----|-------|-------|
| **DOS-kjernen** | `DOS/` | ~75 .ASM | INT 21h systemkall, filhåndtering, minneallokering |
| **BIOS** | `BIOS/` | ~14 .ASM | Maskinavvikling: INT 13h (disk), INT 16h (tastatur), INT 10h (video) |
| **Boot-sektor** | `BOOT/` | 1 .ASM | Laster IBMBIO.COM og IBMDOS.COM |
| **Kommandoer** | `CMD/` | ~30 undermapper | COMMAND.COM, DEBUG, FORMAT, FDISK, m.fl. |
| **Enhetsdrivere** | `DEV/` | ~10 undermapper | SMARTDRV, ANSI.SYS, RAMDRIVE, DISPLAY, KEYBOARD |
| **Hoder** | `INC/`, `H/` | ~20 filer | DPB, BPB, DIRENT, EXE-strukturer |
| **MEMM** | `MEMM/` | ~10 filer | Expanded Memory Manager (XMS/EMS) |

## DOS-kjernen (`DOS/`)

DOS-kjernen implementerer ~80 INT 21h-funksjoner. `DISPATCH.ASM` inneholder dispatch-tabellen som kartlegger hver AH-kode til kildefil:

### Systemkall-grupper (fra `DISPATCH.ASM:30-62`)

| Gruppe | AH-koder | Kildefil | Funksjon |
|--------|----------|----------|----------|
| Konsol-I/O | 01h–0Ch | `CPMIO.ASM` | StdCon Input/Output, Raw I/O, String I/O |
| FCB I/O | 0Dh–18h | `FCBIO.ASM` | File Control Block operasjoner (legacy) |
| Filsystem | 3Ch–44h | `FILE.ASM`, `HANDLE.ASM` | Open, Close, Read, Write, LSeek, ChMod, IOCTL |
| Minne | 48h–4Ah | `ALLOC.ASM` | Alloc, Dealloc, SetBlock |
| Prosess | 4Bh–4Dh | `PROC.ASM`, `EXEC.ASM` | Exec, Exit, Wait |
| Søk | 4Eh–4Fh | `SEARCH.ASM` | FindFirst, FindNext |
| Tid/Dato | 2Ah–2Dh | `TIME.ASM` | Get/Set Date, Get/Set Time |
| Stier | 39h–3Bh | `PATH.ASM` | MkDir, RmDir, ChDir |
| Diverse | 2Fh–38h | `GETSET.ASM`, `MISC.ASM` | GetVersion, GetDPB, DiskReset |

### Kritiske seksjoner

Fra `DISPATCH.ASM:14-25`:
- **critDisk (1)** — Buffer cache operasjoner
- **critDevice (2)** — Enhetsdriver-kall
- **critMem (4)** — Minneallokering
- **critNet (5)** — Nettverksoperasjoner

### Lavnivå-moduler

| Modul | Funksjoner |
|-------|-----------|
| `FAT.ASM` | UNPACK, PACK, MAPCLUSTER, FATREAD_SFT, FATREAD_CDS |
| `BUF.ASM` | Buffer cache: SETVISIT, PLACEBUF, GETBUFFR, FlushBuf |
| `DISK.ASM` | DOS_READ, DOS_WRITE, DISKREAD, DISKWRITE |
| `DIR.ASM` | SEARCH, FindEntry, NEXTENT, GETENTRY, FINDPATH |
| `MKNODE.ASM` | BUILDDIR, NEWENTRY, FREEENT, NEWDIR, DOOPEN |
| `FCB.ASM` | MakeFcb, NameTrans, PATHCHRCMP |
| `CTRLC.ASM` | FATAL, HardErr, DSKSTATCHK, CNTCHAND |
| `DEV.ASM` | IOFUNC, DEVIOCALL, SETREAD, SETWRITE |

## BIOS (`BIOS/`)

BIOS-laget gir maskinavvikling for DOS-kjernen. Linker sammen til `IBMBIO.COM`:

| Fil | Rolle |
|-----|-------|
| `MSBIO1.ASM` | BIOS entry point, device init (CON, AUX, LPT, CLOCK, DISK) |
| `MSBIO2.ASM` | INT 2F hook, disk swap, media checking |
| `MSDISK.ASM` | INT 13h disk I/O: read, write, verify, format, media check |
| `MSCON.ASM` | INT 16h keyboard, INT 10h video console |
| `MSAUX.ASM` | Serial port (COM) I/O |
| `MSLPT.ASM` | Parallel port (LPT) printer I/O |
| `MSCLOCK.ASM` | INT 1Ah real-time clock, CMOS access |
| `MSINIT.ASM` | BIOS init: CMOS clock, day-to-date conversion |
| `MSHARD.ASM` | Hard disk specific routines |
| `SYSCONF.ASM` | CONFIG.SYS parsing |
| `SYSIMES.ASM` | Interrupt handler initialization |
| `SYSINIT1.ASM`, `SYSINIT2.ASM` | System initialization |

## Boot-sektor (`BOOT/`)

`MSBOOT.ASM` er den første koden som kjøres ved oppstart:
- Lastes av BIOS til adresse `7C00h`
- Leser BPB (BIOS Parameter Block) fra boot-sektoren
- Laster `IBMBIO.COM` og `IBMDOS.COM` fra disken
- Overgir kontroll til DOS

## Byggesystem

- **Assembler:** MASM (Microsoft Macro Assembler)
- **Linker:** .LNK-filer per komponent
- **Build:** MAKEFILE per katalog
- **Meldinger:** .SKL (skeleton) filer for språkpakker

## Minnekart

```
00000h  Interrupt Vector Table (IVT)
07C00h  Boot Sector (laster her)
07E00h  IBMBIO.COM (BIOS)
09000h  IBMDOS.COM (DOS-kjerne)
...     System Data Area (DPB, SFT, CDS)
90000h  COMMAND.COM
...     Konvensjonell minne (640K grense)
A0000h  Video RAM
C0000h  ROM BIOS
F0000h  ROM BIOS (boot code)
```
