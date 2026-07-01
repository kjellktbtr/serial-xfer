---
title: Debugging DOS Programs Under an Emulator (qemu / bochs / DOSBox)
type: concept
sources:
  - docs/raw/1/debugging-dos.md
related:
  - "[[dos-agent]]"
  - "[[bare-metal-boot]]"
created: 2026-07-01
updated: 2026-07-01
confidence: medium
---

Techniques for running and inspecting a real-mode DOS binary under a full PC
emulator, ported in from a sibling project's debugging notes. The recipes
are directly reusable for `XFER.COM`; **the specific tool paths in the
source doc are not** — see the caveat below before following any command
literally.

## ⚠️ Source doc references paths that don't exist in serial-xfer

`docs/raw/1/debugging-dos.md` was written for a different project (a "pyc"
compiler with a `single/` DOSBox test harness and `tools/fat12img.py`
helper). None of that exists in this repo. What *is* portable:

- The **qemu/bochs/gdb techniques** themselves (monitor introspection,
  serial file redirection, gdb stub usage) — these are generic emulator
  features, not project-specific.
- The **general approach** to injecting a program onto a bootable floppy
  image and capturing its console/serial output.

What is **not** portable: `tools/fat12img.py`, the `single/serial_smoke.c`
test suite, `docs/progress-log.md` — none of these exist here. If you want
the FAT12-image-injection workflow for serial-xfer, you'd need to either
find/write an equivalent tool, or use DOSBox's built-in directory-mount
(`mount c host_dir`) instead, which sidesteps image manipulation entirely
and is simpler for this project's actual test needs — this project already
tests via emulator-free Unicorn-based `test_com.py`, so a full-PC-emulator
harness is only needed for scenarios Unicorn can't reach (real BIOS/UART
timing quirks, keyboard-abort interaction, actual serial hardware behavior).

## Tools

| Tool | Use |
|------|-----|
| `qemu-system-i386` | Fast boot (~2s). Best for iteration. Non-invasive introspection via `-monitor stdio` and `-serial file:`. gdb stub via `-s -S`. |
| `bochs` (debugger build) | Scriptable debugger with magic breakpoints, but slow (~10⁵ ticks/s under xvfb). |
| `dosbox` | Simple, widely available; serial backends limited to nullmodem/directserial in old versions (no file-based serial capture). |

A bootable FreeDOS floppy image is the common substrate for all three.

## Recipe — run a program under qemu and capture console output

```bash
cp fdboot.img run.img
printf 'XFER.COM > OUT.TXT\r\n' > ae.bat     # redirect console output to a file
# (inject XFER.COM + AUTOEXEC.BAT into run.img using whatever FAT tool you have)
timeout 20 qemu-system-i386 -fda run.img -boot a -display none -no-reboot
# (read OUT.TXT back out of run.img)
```

DOS `> OUT.TXT` redirection works for `INT 21h AH=02` console output (it
routes through file handle 1), which is exactly how `xfercom.asm`'s
`putstr`/`puts` print — so this recipe applies directly to `XFER.COM`'s
banner/status text.

## Recipe — serial round-trip (feed input + log output), no live interaction

This is the recipe most directly relevant to serial-xfer, since the whole
point of `XFER.COM` is serial I/O:

```bash
printf 'some bytes to feed the agent' > /tmp/ser_in.dat
qemu-system-i386 -fda run.img -boot a -display none \
  -chardev file,id=s0,path=/tmp/ser_out.log,input-path=/tmp/ser_in.dat \
  -serial chardev:s0
cat /tmp/ser_out.log     # whatever the guest wrote to COM1
```

- `input-path` → bytes delivered to the guest UART, i.e. what
  `xfercom.asm`'s `uart_getc` reads.
- `path` → the guest's UART transmit (`uart_putc`) is appended here.
- Needs **QEMU ≥ 7.0** for `input-path`.

This is a fully scriptable way to drive `XFER.COM`'s serial protocol without
a second physical machine or a real null-modem cable — feed a raw COBS+CRC
frame in, read the ACK/response frame back out. Complementary to
`test_com.py`'s Unicorn-based approach: Unicorn tests the CPU/instruction
logic in isolation; this recipe tests against a real (emulated) 8250 UART
and real BIOS keyboard polling (`INT 16h`, the 'Q'-abort path).

## Recipe — non-invasive runtime introspection (qemu monitor)

Freeze the running program and dump CPU state without modifying the binary
(important when a bug is timing- or layout-sensitive):

```bash
( sleep 10; echo stop; echo "info registers"; echo "x/8i $eip"; echo quit ) | \
  timeout 25 qemu-system-i386 -fda run.img -boot a -display none -monitor stdio
```

`info registers` gives CS/SS/DS/ESP/EBP at the freeze point.

## Recipe — serial trace via direct UART writes (when instrumentation is acceptable)

```asm
; Emit a byte over COM1 directly, for use as a debug trace point
mov dx, 0x3F8
mov al, byte_to_trace
out dx, al
```

qemu captures this with `-serial file:OUT`. Note this only works cleanly
when adding the instrumentation doesn't itself perturb the bug being
chased (layout-sensitive bugs can shift out of their trigger window when
code size changes) — prefer the qemu-monitor recipe above for anything
layout-sensitive.

## qemu + gdb (hardware watchpoints)

```bash
qemu-system-i386 -fda run.img -boot a -display none -s -S
gdb -batch -ex 'target remote :1234' ...
```

Exposes a gdb stub on `:1234`. Breakpoints/watchpoints are written into live
memory — non-invasive to the on-disk binary layout.

**Gotchas:**
- gdb disassembles 16-bit real-mode code as 32-bit even after
  `set architecture i8086`. Don't trust `x/i`; dump raw bytes
  (`x/NXb <linear-addr>`) and pipe through `ndisasm -b16` instead.
- Segment arithmetic for gdb: `linear = (seg << 4) + offset`
  (real mode has no paging, so linear = physical).
- Example: `x/... ((int)$cs*16)+((int)$eip & 0xffff)`.

**Procedure for catching a specific corrupting write** (generalizes beyond
the FP-corruption bug it was developed for): get the target's load segment
from its entry code, `hbreak` at the routine of interest, read `SS:SP` at
the breakpoint to find a known stack slot (e.g. a return address), then set
a **hardware watchpoint** on that physical address and `continue` — the
watchpoint fires on whatever instruction corrupts it, pinpointing the bug
directly instead of single-stepping blind.

## bochs (scriptable, but slow)

```bash
cat > bochsrc <<EOF
megs: 32
romimage: file=/usr/share/bochs/BIOS-bochs-latest
vgaromimage: file=/usr/share/bochs/VGABIOS-lgpl-latest.bin
floppya: 1_44=run.img, status=inserted
boot: floppy
display_library: x
magic_break: enabled=1
EOF
{ echo c; for i in $(seq 8); do echo sreg; echo r; echo c; done; echo q; } > cmds.txt
xvfb-run -a bochs -q -f bochsrc -rc cmds.txt
```

`magic_break` stops on the `xchg bx, bx` opcode (`87 DB`) inserted anywhere
in the code — a position-independent breakpoint you can drop straight into
NASM source. Budget minutes per run; prefer qemu for anything iterative.

## See also

- [[dos-agent]] — what's actually being debugged: `xfercom.asm`'s structure
- [[bare-metal-boot]] — the boot-sector/floppy-image mechanics these recipes build on
