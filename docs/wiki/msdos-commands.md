---
title: "MS-DOS v4.0 Command Utilities"
type: code-map
sources:
  - MS-DOS/v4.0/src/CMD/
related:
  - "[[msdos-v4-architecture]]"
  - "[[msdos-device-drivers]]"
created: 2026-06-26
updated: 2026-06-26
confidence: high
---

# MS-DOS v4.0 Command Utilities

The `CMD/` directory contains ~30 subdirectories, each implementing a command utility. These are split into **internal commands** (linked into COMMAND.COM), **external commands** (standalone .EXE/.COM files), and **support utilities**.

## Internal Commands (COMMAND.COM)

Built into the command interpreter itself. Source in `CMD/COMMAND/`.

| File | Function | Description |
|------|----------|-------------|
| `COMMAND1.ASM` | Main interpreter loop | Command parsing, redirection, pipe setup |
| `COMMAND2.ASM` | Internal command dispatch | CALLTYPE processing, command execution |
| `COMEQU.ASM` | Equates/definitions | Shared constants for command interpreter |
| `COMSEG.ASM` | Segment definitions | Data/code segment layout |
| `COMSW.ASM` | Switch handling | `/C`, `/Q`, `/P`, `/V` switch parsing |
| `CPARSE.ASM` | Command line parsing | Tokenize input line |
| `COPY.ASM` | COPY command | File copy with concatenation support |
| `COPYPR1.ASM` | COPY processing (part 1) | Source file open/read logic |
| `COPYPR2.ASM` | COPY processing (part 2) | Destination file write/close logic |
| `INIT.ASM` | Initialization | COMMAND.COM entry point, environment setup |
| `IPARSE.ASM` | Internal parse support | Path resolution helpers |
| `PARSE2.ASM` | Extended parsing | Complex path handling |
| `PATH1.ASM`, `PATH2.ASM` | PATH command | Search path management |
| `TCMD1A.ASM`–`TCMD2B.ASM` | Core commands | TYPE, DIR, DEL, REN, CLS, VOL, PROMPT, VER |
| `TFOR.ASM` | FOR command | Loop expansion with wildcard support |
| `TPARSE.ASM` | Command parsing | IF, GOTO, SHIFT processing |
| `TPIPE.ASM` | Pipe handling | `|` pipe creation and management |
| `TSPC.ASM` | Special commands | ECHO, REM, BREAK, VERIFY |
| `TRANMSG.ASM` | Translation messages | Internationalized error messages |
| `TBATCH.ASM`, `TBATCH2.ASM` | Batch processing | `.BAT` file execution engine |
| `TPRINTF.ASM` | Printf support | Formatted output for DIR, VER, etc. |
| `UINIT.ASM` | Utility initialization | Helper function init |
| `TCODE.ASM`, `TUCODE.ASM` | Command code | Additional internal command implementations |
| `TFOR.ASM` | FOR loop | Variable substitution and iteration |
| `TENV.ASM`, `TENV2.ASM` | SET command | Environment variable management |
| `TMISC1.ASM`, `TMISC2.ASM` | Miscellaneous | CD/CHDIR, MD/MKDIR, RD/RMDIR, PUSHD, POPD |
| `IFEQU.ASM` | IF command | Conditional execution logic |
| `FORDATA.ASM` | FOR data | Loop variable storage |
| `ENVDATA.ASM` | Environment data | Variable storage blocks |
| `RDATA.ASM`, `RUCODE.ASM` | Redirection | `>`, `>>`, `<` handling |
| `RESMSG.EQU` | Reserved messages | Error message table |

## External Commands

### File Operations

| Directory | Command | Language | Description |
|-----------|---------|----------|-------------|
| `XCOPY/` | XCOPY | ASM | Extended copy with directory trees, wildcards, attribute filtering |
| `FC/` | FC | C+ASM | File compare (binary and text mode), line-by-line diff |
| `COMP/` | COMP | ASM | Sector-by-sector file comparison (alternative to FC) |
| `FIND/` | FIND | ASM | Text search in files with string/line counting |
| `SORT/` | SORT | ASM | Sort input with key extraction and reverse options |
| `MORE/` | MORE | ASM | Paginated output filter |
| `TREE/` | TREE | ASM | Directory tree display with path visualization |
| `ATTRIB/` | ATTRIB | C+ASM | View/change file attributes (R, H, S, A) |
| `LABEL/` | LABEL | ASM | Create/change disk volume labels |
| `REPLACE/` | REPLACE | C+ASM | Replace files in target directory |

### Disk Utilities

| Directory | Command | Language | Description |
|-----------|---------|----------|-------------|
| `FORMAT/` | FORMAT | ASM | Low-level disk formatting with FAT creation, tracks/sectors geometry |
| `FDISK/` | FDISK | C+ASM | Partition table editor (MBR), primary/extended/logical partition management |
| `CHKDSK/` | CHKDSK | ASM | File system integrity checker: FAT chain validation, directory cross-link detection, free space calculation |
| `RECOVER/` | RECOVER | ASM | Disk recovery: damaged FAT repair, file salvage |
| `DISKCOPY/` | DISKCOPY | ASM | Sector-by-sector disk copy (floppy-to-floppy) |
| `DISKCOMP/` | DISKCOMP | ASM | Sector-by-sector disk comparison |
| `SYS/` | SYS | ASM | Transfer system files (IBMBIO.COM, IBMDOS.COM) to bootable disk |
| `BACKUP/` | BACKUP | C | Archive utility with date/attribute filtering, multi-disk support |
| `RESTORE/` | RESTORE | C | Restore from BACKUP archives (multiple format versions: RTOLD, RTNEW, RTT) |

### System Configuration

| Directory | Command | Language | Description |
|-----------|---------|----------|-------------|
| `MODE/` | MODE | ASM | Configure device parameters: screen modes, serial port settings, printer redirection, country code page |
| `KEYB/` | KEYB | ASM | Keyboard driver loader with country-specific layouts (I9, I2F, I48) |
| `COUNTRY/` | (MKCNTRY) | ASM | Country information file generator |
| `MEM/` | MEM | C | Memory map display: conventional, upper, EMS, XMS usage |
| `SHARE/` | SHARE | ASM | File sharing manager (network support, lock table) |
| `PRINT/` | PRINT | ASM | Spooler daemon for background printing |
| `JOIN/` | JOIN | C | Join drive letters to directory paths (network redirect) |
| `SUBST/` | SUBST | C | Substitute drive letter with path |
| `APPEND/` | APPEND | ASM | Search path for data files (separate from PATH) |
| `ASSIGN/` | ASSIGN | ASM | Redirect file handles between drives |
| `GRAFTABL/` | GRAFTABL | ASM | Graphics character table loader for code page support |

### Development Tools

| Directory | Command | Language | Description |
|-----------|---------|----------|-------------|
| `DEBUG/` | DEBUG | ASM | Interactive debugger: assemble, disassemble, memory edit, register manipulation, program execution |
| `EDLIN/` | EDLIN | ASM | Line-oriented text editor |
| `EXE2BIN/` | EXE2BIN | ASM | Convert EXE header to flat .COM binary |

### Graphics Support

| Directory | Command | Language | Description |
|-----------|---------|----------|-------------|
| `GRAPHICS/` | GRAPHICS.COM | ASM | IBM Graphics API loader: loads .PRO/.EXT graphics driver files for INT 2Fh graphics services |

### File System Support

| Directory | Command | Language | Description |
|-----------|---------|----------|-------------|
| `FILESYS/` | FILESYS | C | Installable file system (IFS) utility |
| `IFSFUNC/` | IFSFUNC | ASM | IFS function library: device/directory/file/link/session support |
| `NLSFUNC/` | NLSFUNC | ASM | National Language Support function library |

### Fast Open/Seek Extensions

| Directory | Command | Language | Description |
|-----------|---------|----------|-------------|
| `FASTOPEN/` | FASTOPEN | ASM | Fast file open extension (bypasses normal path resolution for known paths) |

## Build System

Each command directory contains:
- `MAKEFILE` — MASM build rules
- `*.LNK` — Linker configuration
- `*.SKL` — Skeleton/message file for internationalization
- `*.INC` — Shared include files

## Language Distribution

- **Assembly (MASM)**: ~70% of commands (performance-critical I/O, disk utilities)
- **C**: ~30% of commands (complex parsing, BACKUP/RESTORE, ATTRIB, MEM)
- **Mixed**: FC, FDISK, ATTRIB use C for logic + ASM for message handling

## Key Design Patterns

1. **Message handling**: `.SKL` + `.MSG` files for internationalization; `_MSGRET.ASM` and `_PARSE.ASM` are shared across C commands
2. **Parameter parsing**: `PSDATA.INC` provides a common parser framework (switches, keywords, file specs, drive letters)
3. **Error codes**: Defined in `H/ERROR.H` and `H/UTLERROR.H`
4. **DOS calls**: Via `INT 21h` using macros from `H/DOSCALLS.H`
