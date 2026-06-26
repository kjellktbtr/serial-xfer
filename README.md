# serial-xfer

Move files to and from a vintage **MS-DOS / PC-DOS / FreeDOS** machine over a plain
**serial cable**, and even **mount its filesystem** on your modern box — driven by a
tiny (~2.5 KB) hand-written DOS agent and two Python scripts.

The DOS side is a single freestanding `XFER.COM` (assembled from `xfercom.asm`, no
runtime, no linker). The host side is `host.py` (a `scp`/`rsync`-style file-transfer
tool) and `mountfs.py` (a FUSE filesystem that makes the DOS disk show up under a
local directory). The link is binary-safe, CRC-checked, and resumes through line
noise.

```
┌────────────┐   null-modem serial (COM1, 9600 8N1)   ┌─────────────────────────┐
│ modern host│  <───────────────────────────────────> │ vintage DOS PC          │
│ host.py    │     COBS + CRC-16 + CRC-32 + ACK       │ XFER.COM (listening)    │
│ mountfs.py │                                        │ "press Q to quit"       │
└────────────┘                                        └─────────────────────────┘
```

## Features

- **Binary-safe & verified** — COBS framing, per-packet CRC-16, and a whole-file
  CRC-32 (zlib-compatible) on every transfer. Bad frames are NAK'd and resent;
  failed files are retried until they succeed or you press Ctrl-C.
- **Whole trees** — upload/download directory trees with structure preserved;
  long/illegal names are mangled to unique DOS 8.3 names automatically.
- **`dir` browsing** — list a drive or path, optionally recursively (`dir /s`-style).
- **Live feedback on both ends** — the host shows a pre-transfer summary (per-file
  size + ETA) and dual [tqdm](https://github.com/tqdm/tqdm) progress bars; the DOS
  screen shows a fitted summary and a single 80-column status line that updates in
  place per file.
- **Mount it** — `mountfs.py` mounts the DOS disk as a local FUSE filesystem. It
  eagerly caches all directory metadata in the background, so `ls`/`stat` are
  instant despite the slow link; file contents are fetched on demand.
- **Tiny, self-contained agent** — `XFER.COM` is ~2 KB, needs no DOS extender,
  TSR, or external libraries; just run it. Quit any time with **Q** on the DOS
  keyboard.

## Requirements

- **DOS machine:** any PC with an **8088/8086 or later** CPU and **DOS 2.0+**
  (tested target: PC DOS 3.3), plus a serial port (8250/16550 UART at COM1). The
  agent is assembled `cpu 8086` — no 186/286/386 instructions — and uses only
  standard BIOS/DOS calls, so it runs on the oldest IBM PCs and compatibles.
- A **null-modem serial cable** between the two machines (or an emulator's virtual
  serial port). The agent uses default **COM1** at **9600 8N1**. (supports COM1-4 and up to 115200 baud rate)
- **Host:** Python ≥ 3.12. `pyserial` (real serial ports) and `tqdm` (progress
  bars) are installed by default; `fusepy` + libfuse are needed only for the mount
  tool (`pip install ".[mount]"`).
- **Building the agent:** [`nasm`](https://www.nasm.us/) — but a prebuilt
  `XFER.COM` ships in this repo, so you don't need it just to use the tool.
- **Running the tests:** `unicorn` (`pip install ".[dev]"`) + `nasm`.

With [uv](https://docs.astral.sh/uv/):

```bash
uv sync                      # base: pyserial + tqdm
uv sync --extra mount        # + fusepy for mountfs.py
uv sync --extra dev          # + unicorn for the test suite
```

## Get the agent onto the DOS machine

`XFER.COM` is only ~2 KB, so it fits on any floppy with room to spare — that's
much of the point: keep it on a "toolkit" diskette and you never have to swap
floppies or pull a hard drive again to move a few files.

There's an unavoidable chicken-and-egg the first time: you need *a* way to deliver
the transfer tool before you can use it. Easiest path - get `XFER.COM` onto a floppy
in some way first.

### Bootstrapping via raw serial

Instead of manually typing it in, it can be copied in an emergency with the
`COPY COM1:` command. I think the copy command still stops on 0x1A even with
the /B, but not sure and haven't tested. If it is a problem, the procedure is:

`COPY COM1: file /B` on DOS reads bytes from the serial port and writes them to a
file, stopping when it sees a Ctrl-Z byte (0x1A) — the CP/M-inherited end-of-file
sentinel. The Linux side sends the file followed by `printf '\x1a'` to trigger that
stop. Any 0x1A byte inside the binary is indistinguishable from that terminator, so
`COPY` stops early and the file is silently truncated - retrying will always produce
the same result.

`XFER.COM` contains two such bytes (a jump displacement at file offset 0x75C and a
DOS syscall immediate at 0x8C7), so a direct transfer will never produce an intact
file. The workaround is to substitute those bytes with a harmless placeholder on the
host, transfer the patched copy, then restore the originals on the DOS side using
`DEBUG`.

**1. Create a patched copy on the Linux host:**

```bash
python3 -c "
d = bytearray(open('XFER.COM', 'rb').read())
for off in [0x75c, 0x8c7]:   # 0x1A offsets in the current build
    d[off] = 0xfe             # placeholder — any non-0x1A byte works
open('XFER_P.COM', 'wb').write(d)
"
stty -F /dev/ttyUSB0 9600 raw cs8 -parenb -cstopb -echo
```

**2. On DOS, configure the port and start receiving:**

```
C:\> MODE COM1:9600,N,8,1
C:\> COPY COM1: XFER_P.COM /B
```

**3. Immediately send from Linux:**

```bash
{ cat XFER_P.COM; printf '\x1a'; } > /dev/ttyUSB0
```

**4. Verify the byte count matches** (`ls -l XFER.COM` on the host gives the reference size):

```
C:\> DIR XFER_P.COM
```

If the size differs, delete the file and repeat from step 2.

**5. Patch the two bytes back with DEBUG and rename:**

`DEBUG` loads `.COM` files at segment offset 0x100, so each file offset gains 0x100
when addressed in DEBUG:

```
C:\> DEBUG XFER_P.COM
-E 85C 1A
-E 9C7 1A
-W
-Q
C:\> REN XFER_P.COM XFER.COM
```

`XFER.COM` is now the real agent. All subsequent transfers via `host.py` use COBS
framing and full CRC verification - this raw bootstrap is a one-time step.

### Running the agent

No arguments, one argument (baud rate) and two arguments (baud and COM number):
```
C:\> XFER
xfer ready on COM1 at 9600 baud - press Q to quit

C:\> XFER 19200
xfer ready on COM1 at 19200 baud - press Q to quit

C:\> XFER 9600 2
xfer ready on COM2 at 9600 baud - press Q to quit
```

The banner always echoes the port and baud in use. Optional arguments let you
choose a baud rate and/or COM port without recompiling:

| Syntax | Effect |
|--------|--------|
| `XFER` | COM1, 9600 baud (defaults) |
| `XFER baud` | COM1, specified baud |
| `XFER baud com` | Specified baud and COM port (1–4) |

Supported baud rates are any N where 115200 / N is an integer. Common choices:

| Baud | `host.py` flag | Notes |
|------|----------------|-------|
| 9600 | `--baud 9600` | Default; reliable on all hardware including 4.77 MHz 8088. Got approximately 860 bytes / second |
| 19200 | `--baud 19200` | Works reliably on most machines |
| 38400 | `--baud 38400` | Comfortable on 286 and faster |
| 57600 | `--baud 57600` | Approaches the limit of many 8250 UARTs. Didn't observe significant transfer speed increase from floppies or hard drive on the IBM 5155 compared to using 38400. Saturated around 1500 bytes / second. |
| 115200 | `--baud 115200` | Did not work reliably on the IBM 5155 in testing. Some communication worked, but it got stuck before file transfer started. Maybe it weren't able to keep up? |

Press **Q** at any time to exit cleanly, even mid-transfer. Invalid arguments
print a usage message and exit.

## Hardware & cabling

This tool is aimed squarely at machines whose easiest (or only) link to the modern
world is an RS-232 serial port — the original **IBM PC 5150** and **Portable PC
5155** (8088), and the many later PCs that have only a 3.5"/5.25" floppy and a
serial port: no USB, no network. For those, a serial cable beats copying to floppies
or shuttling a hard drive into a newer machine and back.

**Connectors.** The IBM Asynchronous Communications Adapter in those PCs uses a
**DB-25 male** port; modern USB-serial dongles are **DB-9**. So you want a
null-modem cable/adapter that bridges **DB25 ↔ DB9**.

**A 3-wire cable is enough.** XFER paces the link with **software ACKs, not hardware
flow control**, so you only need three wires crossed null-modem style:

```
   DB-9 (modern)              DB-25 (IBM PC)
   2  RxD  <───────────────  2  TxD
   3  TxD  ───────────────>  3  RxD
   5  GND  <──────────────>  7  GND
```

The agent raises DTR/RTS but never waits on CTS/DSR, so the handshake lines can be
left unconnected (or looped back locally if a stubborn UART/driver insists on
seeing them).

**Port base.** The agent defaults to **COM1** (I/O base 0x3F8), the IBM PC/XT
standard. Pass a COM port number as the second argument to use COM2–COM4 instead
(e.g. `XFER 9600 2` for COM2 at 9600 baud). All four standard bases are supported
(COM1 0x3F8 · COM2 0x2F8 · COM3 0x3E8 · COM4 0x2E8).

**Speed.** 9600 8N1 (~0.8 KB/s effective) is a deliberately safe default: a 4.77 MHz
8088 polls the UART comfortably at that rate, and the stop-and-wait protocol means
there's no overrun risk even on the slowest machine. It's slow for big files, but
these systems mostly move small ones. If a given pair of machines proves rock-solid,
pass a higher baud rate as the first argument (e.g. `XFER 38400`) and match with
`--baud` on the host. See the baud rate table above for tested values. 9600 will
never let you down.

## File-transfer tool — `host.py`

Pick how you reach the agent:

- `--port /dev/ttyUSB0` (or `COM3`, etc.) — a real serial port (needs `pyserial`).
- `--tcp HOST:PORT` — an emulator exposing COM1 as a TCP socket.
- `--socket /path` — an emulator exposing COM1 as a Unix socket.
- `--baud` (default 9600).

```bash
# upload files and/or a whole directory tree (structure preserved on DOS)
python host.py --port /dev/ttyUSB0 upload ./mydir ./notes.txt

# download a single file
python host.py --port /dev/ttyUSB0 download GOT.TXT ./got.txt

# download a whole remote tree, recursively, into ./pulled
python host.py --port /dev/ttyUSB0 download DOS ./pulled --tree

# list files DOS-style: a drive root, a path, or recursively
python host.py --port /dev/ttyUSB0 dir A:
python host.py --port /dev/ttyUSB0 dir C:\DOS -r

# also write the transfer report to a file, then tell the agent to exit
python host.py --port /dev/ttyUSB0 --report run.txt upload ./mydir
python host.py --port /dev/ttyUSB0 quit
```

During a transfer the host prints a full summary (every file's size + estimated
time at ~800 B/s effective, and the total), then dual tqdm bars (overall + current
file). The DOS screen shows a screen-fitted summary that stays put, plus one
fixed 80-column line below it that rewrites in place per file:

```
DOS\QBASIC.EXE                               190k  118:17 [#       3%         ]
```

(name+path · size in KB · total ETA `M:SS` · a bar with the overall % centred).
Failed files are retried indefinitely; **Ctrl-C** stops and prints the report
(including which files were still pending).

## Mount tool — `mountfs.py`

Mount the DOS disk as a local filesystem (needs the `[mount]` extra + libfuse):

```bash
mkdir -p /mnt/dos
python mountfs.py --port /dev/ttyUSB0 /mnt/dos --root 'C:\'
# (or --tcp / --socket, like host.py)
```

Then use normal tools — browsing is instant once the background crawl finishes:

```bash
ls -R /mnt/dos
cp /mnt/dos/AUTOEXEC.BAT .
echo "hi" > /mnt/dos/NOTES.TXT
mkdir /mnt/dos/TEMP
rm /mnt/dos/OLD.TXT
fusermount -u /mnt/dos          # unmount (also tells the agent to quit)
```

How it works: a background thread breadth-first crawls **all** directory metadata
into memory, so `getattr`/`readdir` never touch the wire after the initial crawl.
File contents are read on demand (ranged reads) and written through (ranged
writes). This is safe to cache because a DOS box is single-tasking and **only this
program** mutates it while mounted, so the in-memory tree stays authoritative.

## Building the agent

A prebuilt `XFER.COM` is included. To rebuild after editing `xfercom.asm`:

```bash
nasm -f bin xfercom.asm -o XFER.COM     # ~2 KB flat binary, no linker
# or:
make
```

## Wire protocol

A binary-safe stop-and-wait protocol: `COBS(packet)+0x00` frames, each packet
`TYPE SEQ DATA CRC16`, paced by ACK/NAK, with a whole-file CRC-32 check. See
**[PROTOCOL.md](PROTOCOL.md)** for the full specification (framing, all packet
types, byte layouts, and notes for porting the agent).

## Testing

`test_com.py` is an **emulator-free** regression suite: it assembles `xfercom.asm`
and runs the agent's actual 16-bit machine code under [Unicorn](https://www.unicorn-engine.org/),
driving it with `host.py` and an in-memory fake DOS — no hardware or DOSBox needed.

```bash
uv run --extra dev python test_com.py     # or: pip install ".[dev]" && python test_com.py
```

To exercise it against a real DOS emulator instead, `run_dosbox.sh` builds the COM
and launches DOSBox with COM1 on a TCP nullmodem (`dosbox-xfer.conf`); then drive it
with `host.py --tcp 127.0.0.1:4555`. (DOSBox needs `transparent:1` on the nullmodem
so the binary stream isn't corrupted by line-state bytes.)

## Limitations

- DOS filenames are **8.3** (≤12 chars), upper-case; the host mangles longer host
  names to unique 8.3 names.
- The protocol carries **no timestamps**, so mounted files get synthesized times.
- The mount assumes it is the **only writer** while mounted (true for a
  single-tasking DOS box).
- COM port (1–4) and baud rate are command-line arguments; no recompile needed.

## License

GPL-2.0-only. See [LICENSE](LICENSE). © 2026 Kjell Kristian Grane Torgersen.
Contributions and bug reports welcome via the project's issue tracker.
