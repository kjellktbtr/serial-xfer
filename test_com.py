#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 Kjell Kristian Grane Torgersen
"""Emulator-free regression test for the hand-written XFER.COM (xfercom.asm).

DOSBox/QEMU need a full machine; this instead executes the COM's actual 16-bit
machine code under Unicorn and drives it with host.py, so it runs anywhere
(incl. CI).  Three layers:

  1. codecs   — crc16, crc32, cobs_encode/decode vs host.py over many inputs
  2. framing  — send_packet / read_frame produce/parse host.py frames
  3. e2e      — run main() with COM1 + INT 21h hooked to an in-memory DOS, then
                upload -> download -> list -> quit via host.py's Link

Requires: nasm, and `pip install unicorn`.  The DOSBox path (real serial) is in
dosbox-xfer.conf + run_dosbox.sh.
"""

from __future__ import annotations

import contextlib
import io
import random
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

try:
    from unicorn import UC_ARCH_X86, UC_HOOK_INSN, UC_HOOK_INTR, UC_MODE_16, Uc
    from unicorn.x86_const import (
        UC_X86_INS_IN,
        UC_X86_INS_OUT,
        UC_X86_REG_AH,
        UC_X86_REG_AL,
        UC_X86_REG_AX,
        UC_X86_REG_BX,
        UC_X86_REG_CS,
        UC_X86_REG_CX,
        UC_X86_REG_DI,
        UC_X86_REG_DS,
        UC_X86_REG_DX,
        UC_X86_REG_EFLAGS,
        UC_X86_REG_ES,
        UC_X86_REG_SI,
        UC_X86_REG_SP,
        UC_X86_REG_SS,
    )
except ImportError:
    sys.exit("this test needs the 'unicorn' package:  pip install unicorn")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import host  # noqa: E402

MEM = 0x110000
SENTINEL = 0xFFF0
IN_ADDR, OUT_ADDR = 0x8000, 0xC000
DATA_PORT, LCR_PORT, LSR_PORT = 0x3F8, 0x3FB, 0x3FD


def build() -> tuple[bytes, dict[str, int]]:
    """Assemble xfercom.asm to a COM and return (image, symbol->offset)."""
    tmp = Path(tempfile.mkdtemp())
    com, mp = tmp / "XFER.COM", tmp / "xfer.map"
    wrap = tmp / "wrap.asm"
    wrap.write_text(f'[map symbols {mp}]\n%include "{HERE / "xfercom.asm"}"\n')
    subprocess.run(
        ["nasm", "-w-zeroing", "-f", "bin", str(wrap), "-o", str(com)], check=True
    )
    sym = {}
    for line in mp.read_text().splitlines():
        p = line.split()
        if len(p) == 3 and "." not in p[2]:
            with contextlib.suppress(ValueError):
                sym[p[2]] = int(p[0], 16)
    return com.read_bytes(), sym


COM, SYM = build()


# --- layer 1 + 2: call a single routine, stopping at a sentinel return -------
def _fresh(rx=b""):
    uc = Uc(UC_ARCH_X86, UC_MODE_16)
    uc.mem_map(0, MEM)
    uc.mem_write(0x100, COM)
    for r in (UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS):
        uc.reg_write(r, 0)
    uc.mem_write(0xFEFE, SENTINEL.to_bytes(2, "little"))
    uc.reg_write(UC_X86_REG_SP, 0xFEFE)
    return uc


def _intr_nokey(uc, intno, _ud):
    """Answer the agent's keyboard poll (INT 16h/AH=01h) with 'no key' (ZF=1)."""
    if intno == 0x16 and uc.reg_read(UC_X86_REG_AH) == 0x01:
        uc.reg_write(UC_X86_REG_EFLAGS, uc.reg_read(UC_X86_REG_EFLAGS) | 0x40)


def test_codecs():
    rng = random.Random(1234)
    cases = [
        b"",
        b"\x00",
        b"A",
        b"\x00\x00\x00",
        bytes(range(256)),
        b"\xff" * 300,
        bytes(300),
        b"hi\x00there",
    ]
    cases += [
        bytes(rng.randrange(256) for _ in range(rng.randrange(520))) for _ in range(60)
    ]
    for d in cases:
        uc = _fresh()
        uc.mem_write(IN_ADDR, d or b"\0")
        uc.reg_write(UC_X86_REG_SI, IN_ADDR)
        uc.reg_write(UC_X86_REG_CX, len(d))
        uc.emu_start(SYM["crc16"], SENTINEL)
        assert uc.reg_read(UC_X86_REG_AX) & 0xFFFF == host.crc16(d)

        uc = _fresh()
        uc.mem_write(IN_ADDR, d or b"\0")
        uc.reg_write(UC_X86_REG_SI, IN_ADDR)
        uc.reg_write(UC_X86_REG_CX, len(d))
        uc.reg_write(UC_X86_REG_AX, 0)
        uc.reg_write(UC_X86_REG_DX, 0)
        uc.emu_start(SYM["crc32"], SENTINEL)
        got = ((uc.reg_read(UC_X86_REG_DX) & 0xFFFF) << 16) | (
            uc.reg_read(UC_X86_REG_AX) & 0xFFFF
        )
        assert got == host.crc32(d)

        if len(d) <= 550:
            uc = _fresh()
            uc.mem_write(IN_ADDR, d or b"\0")
            uc.reg_write(UC_X86_REG_SI, IN_ADDR)
            uc.reg_write(UC_X86_REG_CX, len(d))
            uc.reg_write(UC_X86_REG_DI, OUT_ADDR)
            uc.emu_start(SYM["cobs_encode"], SENTINEL)
            enc = bytes(uc.mem_read(OUT_ADDR, uc.reg_read(UC_X86_REG_AX) & 0xFFFF))
            assert enc == host.cobs_encode(d)
            uc = _fresh()
            uc.mem_write(IN_ADDR, enc)
            uc.reg_write(UC_X86_REG_SI, IN_ADDR)
            uc.reg_write(UC_X86_REG_CX, len(enc))
            uc.reg_write(UC_X86_REG_DI, OUT_ADDR)
            uc.emu_start(SYM["cobs_decode"], SENTINEL)
            assert (
                bytes(uc.mem_read(OUT_ADDR, uc.reg_read(UC_X86_REG_AX) & 0xFFFF)) == d
            )
    print(f"  codecs:  {len(cases)} cases OK (crc16, crc32, cobs encode/decode)")


def test_framing():
    rng = random.Random(7)
    n = 0
    for t in (0x01, 0x02, 0x03, 0x10, 0x08):
        for s in (0, 1, 255):
            for d in (
                b"",
                b"A",
                b"\x00\x00",
                bytes(range(20)),
                bytes(rng.randrange(256) for _ in range(rng.randrange(1, 200))),
            ):
                n += 1
                # send_packet
                uc = _fresh()
                # parse_args sets v_base at runtime; direct calls need it pre-set
                uc.mem_write(SYM["v_base"], (0x3F8).to_bytes(2, "little"))
                tx = bytearray()
                uc.hook_add(
                    UC_HOOK_INSN, lambda u, p, sz, ud: 0x20, None, 1, 0, UC_X86_INS_IN
                )
                uc.hook_add(
                    UC_HOOK_INSN,
                    lambda u, p, sz, v, ud: (
                        tx.append(v & 0xFF) if p == DATA_PORT else None
                    ),
                    None,
                    1,
                    0,
                    UC_X86_INS_OUT,
                )
                uc.mem_write(IN_ADDR, d or b"\0")
                uc.reg_write(UC_X86_REG_BX, ((s & 0xFF) << 8) | t)
                uc.reg_write(UC_X86_REG_SI, IN_ADDR)
                uc.reg_write(UC_X86_REG_CX, len(d))
                uc.emu_start(SYM["send_packet"], SENTINEL)
                assert bytes(tx) == host.make_frame(t, s, d)
                assert host.parse_packet(bytes(tx)[:-1]) == (t, s, d)

                # read_frame
                frame = host.make_frame(t, s, d)
                rxq = list(frame)
                uc = _fresh()
                uc.mem_write(SYM["v_base"], (0x3F8).to_bytes(2, "little"))
                uc.hook_add(
                    UC_HOOK_INSN,
                    lambda u, p, sz, ud: (
                        (0x20 | (0x01 if rxq else 0))
                        if p == LSR_PORT
                        else (rxq.pop(0) if rxq else 0)
                    ),
                    None,
                    1,
                    0,
                    UC_X86_INS_IN,
                )
                uc.hook_add(UC_HOOK_INTR, _intr_nokey)  # uart_getc polls INT 16h
                uc.emu_start(SYM["read_frame"], SENTINEL)
                got = bytes(uc.mem_read(SYM["pk"], uc.reg_read(UC_X86_REG_AX) & 0xFFFF))
                assert got == host.cobs_decode(frame[:-1])
    print(f"  framing: {n} cases OK (send_packet / read_frame vs host.py)")


# --- layer 3: full main() with an in-memory DOS ------------------------------
class _Chan:
    def __init__(self):
        self.q = deque()
        self.cv = threading.Condition()

    def put(self, b):
        with self.cv:
            self.q.append(b)
            self.cv.notify_all()

    def get(self):
        with self.cv:
            return self.q.popleft() if self.q else 0


class _FakeDos:
    def __init__(self, uc):
        self.uc = uc
        self.fs = {}
        self.handles = {}
        self.next_h = 5
        self.dta = 0
        self.finds = []
        self.console = bytearray()
        self.exited = None
        self.keys = deque()  # pending BIOS keystrokes (ASCII codes)
        self.ftimes: dict[str, tuple[int, int]] = {}  # name -> (fat_time, fat_date)

    def _cf(self, s):
        f = self.uc.reg_read(UC_X86_REG_EFLAGS)
        self.uc.reg_write(UC_X86_REG_EFLAGS, (f | 1) if s else (f & ~1))

    def _zf(self, s):  # zero flag = EFLAGS bit 6
        f = self.uc.reg_read(UC_X86_REG_EFLAGS)
        self.uc.reg_write(UC_X86_REG_EFLAGS, (f | 0x40) if s else (f & ~0x40))

    def _str(self, off):
        out = bytearray()
        while c := self.uc.mem_read(off, 1)[0]:
            out.append(c)
            off += 1
        return out.decode("latin1")

    def _path(self, off):
        """Uppercase path with any leading drive ('A:') and root '\\' stripped, so
        this single in-memory FS answers both driveless and drive-qualified paths."""
        s = self._str(off).upper().replace("/", "\\")
        if len(s) >= 2 and s[1] == ":":
            s = s[2:]
        return s.lstrip("\\")

    def intr(self, uc, intno, _ud):
        if intno == 0x16:  # BIOS keyboard
            ah = uc.reg_read(UC_X86_REG_AH)
            if ah == 0x01:  # peek: ZF=1 -> no key
                if self.keys:
                    uc.reg_write(UC_X86_REG_AX, self.keys[0])
                    self._zf(False)
                else:
                    self._zf(True)
            elif ah == 0x00:  # read/consume
                uc.reg_write(UC_X86_REG_AX, self.keys.popleft() if self.keys else 0)
            return
        if intno != 0x21:
            return
        ah, al = uc.reg_read(UC_X86_REG_AH), uc.reg_read(UC_X86_REG_AL)
        bx, cx, dx = (
            uc.reg_read(r) for r in (UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DX)
        )
        if ah == 0x02:
            self.console.append(dx & 0xFF)
        elif ah == 0x4C:
            self.exited = al
            uc.emu_stop()
        elif ah == 0x3C:
            name = self._path(dx)
            self.fs[name] = b""
            h = self.next_h
            self.next_h += 1
            self.handles[h] = [name, 0, True]
            uc.reg_write(UC_X86_REG_AX, h)
            self._cf(False)
        elif ah == 0x3D:
            name = self._path(dx)
            if name not in self.fs:
                uc.reg_write(UC_X86_REG_AX, 2)
                self._cf(True)
                return
            h = self.next_h
            self.next_h += 1
            self.handles[h] = [name, 0, (al & 3) != 0]  # AL: 0=ro,1=wo,2=rw
            uc.reg_write(UC_X86_REG_AX, h)
            self._cf(False)
        elif ah == 0x3E:
            self.handles.pop(bx, None)
            uc.reg_write(UC_X86_REG_AX, 0)
            self._cf(False)
        elif ah == 0x3F:
            h = self.handles.get(bx)
            if not h:
                uc.reg_write(UC_X86_REG_AX, 0)
                self._cf(True)
                return
            data = self.fs[h[0]][h[1] : h[1] + cx]
            uc.mem_write(dx, data)
            h[1] += len(data)
            uc.reg_write(UC_X86_REG_AX, len(data))
            self._cf(False)
        elif ah == 0x40:  # write at handle position; CX=0 truncates to position
            h = self.handles.get(bx)
            buf = bytes(uc.mem_read(dx, cx)) if cx else b""
            cur = self.fs.get(h[0], b"")
            if cx == 0:
                self.fs[h[0]] = cur[: h[1]]
            else:
                if len(cur) < h[1]:
                    cur = cur + b"\x00" * (h[1] - len(cur))  # gap-fill past EOF
                self.fs[h[0]] = cur[: h[1]] + buf + cur[h[1] + cx :]
                h[1] += cx
            uc.reg_write(UC_X86_REG_AX, cx)
            self._cf(False)
        elif ah == 0x42:  # lseek (AL=whence; only SEEK_SET used) -> DX:AX
            h = self.handles.get(bx)
            pos = (cx << 16) | dx
            if h:
                h[1] = pos
            uc.reg_write(UC_X86_REG_AX, pos & 0xFFFF)
            uc.reg_write(UC_X86_REG_DX, (pos >> 16) & 0xFFFF)
            self._cf(False)
        elif ah == 0x41:  # delete file
            name = self._path(dx)
            if name in self.fs:
                del self.fs[name]
                self._cf(False)
            else:
                uc.reg_write(UC_X86_REG_AX, 2)
                self._cf(True)
        elif ah == 0x3A:  # rmdir (empty only)
            d = self._path(dx)
            if any(p.startswith(d + "\\") for p in self.fs):
                uc.reg_write(UC_X86_REG_AX, 5)
                self._cf(True)
            else:
                self._cf(False)
        elif ah == 0x56:  # rename old (DS:DX) -> new (ES:DI)
            old = self._path(dx)
            new = self._path(uc.reg_read(UC_X86_REG_DI))
            moved = {
                (new + p[len(old) :] if p == old or p.startswith(old + "\\") else p): c
                for p, c in self.fs.items()
            }
            if moved.keys() == self.fs.keys() and old not in self.fs:
                uc.reg_write(UC_X86_REG_AX, 2)
                self._cf(True)
            else:
                self.fs = moved
                self._cf(False)
        elif ah == 0x39:
            self._cf(False)
        elif ah == 0x57:  # get/set file date and time
            h = self.handles.get(bx)
            if h is None:
                uc.reg_write(UC_X86_REG_AX, 6)
                self._cf(True)
                return
            name = h[0]
            if al == 0:  # get
                ft = self.ftimes.get(name, (0, 0))
                uc.reg_write(UC_X86_REG_CX, ft[0])  # packed time
                uc.reg_write(UC_X86_REG_DX, ft[1])  # packed date
                self._cf(False)
            elif al == 1:  # set
                self.ftimes[name] = (cx, dx)
                self._cf(False)
        elif ah == 0x1A:
            self.dta = dx
        elif ah == 0x4E:
            spec = self._path(dx)
            d = spec.rsplit("\\", 1)[0] if "\\" in spec else ""
            self.finds = self._children(d)
            self._emit(uc)
        elif ah == 0x4F:
            self._emit(uc)
        else:
            uc.reg_write(UC_X86_REG_AX, 0)
            self._cf(False)

    def _children(self, d):
        """Immediate child files (attr 0x20) and subdirs (attr 0x10) of dir `d`."""
        files, dirs = [], set()
        for p, c in self.fs.items():
            if d == "":
                rel = p
            elif p.startswith(d + "\\"):
                rel = p[len(d) + 1 :]
            else:
                continue
            if "\\" in rel:
                dirs.add(rel.split("\\")[0])
            else:
                files.append((rel, len(c), 0x20))
        return files + [(n, 0, 0x10) for n in sorted(dirs)]

    def _emit(self, uc):
        if not self.finds:
            uc.reg_write(UC_X86_REG_AX, 18)
            self._cf(True)
            return
        name, size, attr = self.finds.pop(0)
        ft = self.ftimes.get(name, (0, 0))
        uc.mem_write(self.dta + 21, bytes([attr]))
        uc.mem_write(self.dta + 22, ft[0].to_bytes(2, "little"))  # packed time
        uc.mem_write(self.dta + 24, ft[1].to_bytes(2, "little"))  # packed date
        uc.mem_write(self.dta + 26, size.to_bytes(4, "little"))
        uc.mem_write(self.dta + 30, name.encode("latin1") + b"\x00")
        uc.reg_write(UC_X86_REG_AX, 0)
        self._cf(False)


class _Transport:
    timeout_cls = TimeoutError

    def __init__(self, to_dos, from_dos):
        self.to_dos, self.from_dos = to_dos, from_dos
        self._buf = bytearray()

    def send(self, data):
        for b in data:
            self.to_dos.put(b)

    def read_until(self, term, timeout=5.0):
        end = time.time() + timeout
        while term not in self._buf:
            if not self.from_dos.q:
                if time.time() >= end:
                    break
                time.sleep(0.001)
                continue
            while self.from_dos.q:
                self._buf.append(self.from_dos.get())
        i = self._buf.find(term)
        if i < 0:
            out, self._buf = bytes(self._buf), bytearray()
            return out
        out = bytes(self._buf[: i + 1])
        del self._buf[: i + 1]
        return out


def _boot(seed=None, keys=None):
    """Boot the agent's main() under Unicorn with COM1 + INT 21h/16h hooked to an
    in-memory DOS; return (dos, link, thread) once the banner has printed."""
    uc = _fresh()
    uc.reg_write(UC_X86_REG_SP, 0xFFFE)
    # Set up a minimal PSP command tail so parse_args sees "no arguments" and uses
    # defaults (9600 baud, COM1).  DOS convention: byte at 0x80 = tail length,
    # then the tail ends with CR (0x0D).  Unicorn zeroes memory, but 0x00 ≠ CR,
    # so parse_args would mis-parse it as a bad argument without this setup.
    uc.mem_write(0x80, bytes([0, 0x0D]))
    to_dos, from_dos = _Chan(), _Chan()
    dlab = [False]

    def hin(u, port, sz, _ud):
        if port == LSR_PORT:
            if not to_dos.q:
                time.sleep(0.0005)
            return 0x20 | (0x01 if to_dos.q else 0)  # THR always empty
        return to_dos.get() if port == DATA_PORT else 0

    def hout(u, port, sz, val, _ud):
        if port == LCR_PORT:
            dlab[0] = bool(val & 0x80)
        elif port == DATA_PORT and not dlab[0]:
            from_dos.put(val & 0xFF)

    dos = _FakeDos(uc)
    if seed:
        dos.fs.update(seed)
    if keys:
        dos.keys.extend(keys)
    uc.hook_add(UC_HOOK_INSN, hin, None, 1, 0, UC_X86_INS_IN)
    uc.hook_add(UC_HOOK_INSN, hout, None, 1, 0, UC_X86_INS_OUT)
    uc.hook_add(UC_HOOK_INTR, dos.intr)
    th = threading.Thread(target=lambda: uc.emu_start(0x100, 0, 0, 0), daemon=True)
    th.start()
    deadline = time.time() + 15
    while b"COM1" not in bytes(dos.console) and time.time() < deadline:
        time.sleep(0.02)
    link = host.Link(_Transport(to_dos, from_dos), retries=10, timeout=8.0)
    link.query_version()  # detect v1 date/time support; sets link.proto_version
    return dos, link, th


def test_e2e():
    dos, link, th = _boot()
    payload = bytes(range(256)) * 4 + b"\x00\x00null\x00bytes\x00here\x00END"
    src = Path(tempfile.mktemp())
    src.write_bytes(payload)

    n = link.upload_file_once(src, "SUB\\TEST.BIN")
    dst = Path(tempfile.mktemp())
    m = link.download_file_once("SUB\\TEST.BIN", dst)
    entries = link.list_dir("SUB\\*.*")
    link.message("hello-target")  # host-driven on-screen text (#1)
    link.quit()
    th.join(timeout=5.0)

    assert n == len(payload) and m == len(payload)
    assert dst.read_bytes() == payload, "round-trip payload mismatch"
    # entries are (name, attr, size, mtime) 4-tuples in protocol v1
    assert any(e[:3] == ("TEST.BIN", 0x20, len(payload)) for e in entries), (
        f"bad listing {entries}"
    )
    con = dos.console.decode("latin1")
    assert "press Q to quit" in con, "startup banner/quit hint missing"
    assert "hello-target" in con, "T_MSG text was not displayed on target"
    assert dos.exited == 0
    print(
        f"  e2e:     upload+download {n}B round-trip OK, list={entries}, "
        f"T_MSG shown, clean QUIT"
    )


def test_keyboard_quit():
    dos, _link, th = _boot()
    assert dos.exited is None  # still running after boot
    dos.keys.append(ord("q"))  # operator presses 'q'
    th.join(timeout=5.0)
    assert dos.exited == 0, "agent did not exit on keyboard 'q'"
    print("  keyquit: agent exits cleanly on keyboard 'q' (no QUIT packet)")


def test_midstream_quit():
    # Agent is serving a download (in serve_get's wait_ack) when the host sends a
    # QUIT instead of an ACK — it must still exit cleanly (#4).
    dos, link, th = _boot(seed={"GET.BIN": bytes(range(200))})
    link.xact(host.T_GET, b"GET.BIN")  # ACKed; agent now streams DATA
    first = link._read_frame()  # the first DATA frame
    assert host.parse_packet(first)[0] == host.T_DATA
    link.t.send(host.make_frame(host.T_QUIT, 0))  # QUIT mid-stream (not an ACK)
    th.join(timeout=5.0)
    assert dos.exited == 0, "agent stuck: QUIT mid-stream was not honoured"
    print("  midquit: QUIT honoured mid-stream (serve_get wait_ack) -> clean exit")


def test_dir_and_queue():
    # Seed a small tree on the target and exercise the host's recursive dir
    # listing + the run_queue path (which pushes filename/result messages).
    seed = {"README.TXT": b"hi", "SUB\\INNER.DAT": bytes(50)}
    dos, link, th = _boot(seed=seed)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        link.print_dir("A:", recursive=True)
    out = buf.getvalue()
    assert "README.TXT" in out and "<DIR>" in out and "INNER.DAT" in out, out

    # run_queue path: upload a file (sends the summary + live progress line).
    src = Path(tempfile.mktemp())
    src.write_bytes(b"queue-payload" * 20)
    report = host.TransferReport()
    with contextlib.redirect_stdout(io.StringIO()):
        link.run_queue(
            [host._Job("up", src, "Q.BIN", src.stat().st_size)], report, progress=False
        )
    assert "Q.BIN" in dos.fs and dos.fs["Q.BIN"] == src.read_bytes()
    con = dos.console.decode("latin1")
    assert "Q.BIN" in con and "%" in con, "summary/progress line not shown on target"

    link.quit()
    th.join(timeout=5.0)
    print("  dir/que: recursive dir listing + run_queue messages OK")


def test_v2():
    base = bytes(range(256)) * 2  # 512 bytes
    dos, link, th = _boot(
        seed={"DATA.BIN": bytes(base), "OLD.TXT": b"rename me", "JUNK.DAT": b"x"}
    )

    # ranged read at an offset, spanning >CHUNK so the host loops
    assert link.pread("DATA.BIN", 100, 300) == base[100:400], "pread mismatch"

    # ranged write overwriting a middle region
    link.pwrite("DATA.BIN", 10, b"\xaa" * 20)
    exp = bytearray(base)
    exp[10:30] = b"\xaa" * 20
    assert link.pread("DATA.BIN", 0, 512) == bytes(exp), "pwrite mismatch"

    # create empty, grow, then truncate (shrink)
    link.create_empty("NEW.BIN")
    assert dos.fs["NEW.BIN"] == b""
    link.pwrite("NEW.BIN", 0, b"hello world")
    assert dos.fs["NEW.BIN"] == b"hello world"
    link.truncate("NEW.BIN", 5)
    assert dos.fs["NEW.BIN"] == b"hello"

    link.delete("JUNK.DAT")
    assert "JUNK.DAT" not in dos.fs

    link.rename("OLD.TXT", "NEW.TXT")
    assert "OLD.TXT" not in dos.fs and dos.fs["NEW.TXT"] == b"rename me"

    # rmdir: refuses a non-empty dir, succeeds once empty
    dos.fs["SUB\\A.TXT"] = b"q"
    try:
        link.rmdir("SUB")
        raise AssertionError("rmdir of non-empty dir should fail")
    except OSError:
        pass
    link.delete("SUB\\A.TXT")
    link.rmdir("SUB")

    link.quit()
    th.join(timeout=5.0)
    assert dos.exited == 0
    print("  v2:      pread/pwrite/create/truncate/delete/rename/rmdir OK")


def test_mountfs():
    import mountfs

    dos, link, th = _boot(
        seed={
            "README.TXT": b"hello readme",
            "DOS\\EDIT.COM": bytes(300),
            "DOS\\HELP\\X.TXT": b"deep file",
        }
    )
    rfs = mountfs.RemoteFS(link, root="C:\\")
    rfs.start()
    rfs._crawler.join(timeout=10)

    # browsing comes from the cache (BFS-crawled)
    assert set(rfs.readdir("/")) >= {"README.TXT", "DOS"}
    assert set(rfs.readdir("/DOS")) >= {"EDIT.COM", "HELP"}
    assert rfs.readdir("/DOS/HELP") == ["X.TXT"]
    assert rfs.getattr("/DOS").is_dir
    assert rfs.getattr("/README.TXT").size == 12

    # content fetched on demand (ranged read)
    assert rfs.read("/README.TXT", 100, 0) == b"hello readme"
    assert rfs.read("/DOS/HELP/X.TXT", 4, 5) == b"file"

    # create + write-through + size update
    rfs.create("/NEW.TXT")
    assert "NEW.TXT" in rfs.readdir("/")
    rfs.write("/NEW.TXT", b"written data", 0)
    assert dos.fs["NEW.TXT"] == b"written data"
    assert rfs.getattr("/NEW.TXT").size == 12

    # mkdir / rmdir
    rfs.mkdir("/MYDIR")
    assert "MYDIR" in rfs.readdir("/")
    rfs.rmdir("/MYDIR")
    assert "MYDIR" not in rfs.readdir("/")

    # rename + unlink
    rfs.rename("/README.TXT", "/READ2.TXT")
    assert "READ2.TXT" in rfs.readdir("/") and "README.TXT" not in rfs.readdir("/")
    assert dos.fs["READ2.TXT"] == b"hello readme"
    rfs.unlink("/READ2.TXT")
    assert "READ2.TXT" not in rfs.readdir("/")

    link.quit()
    th.join(timeout=5.0)
    print(
        "  mount:   RemoteFS crawl + getattr/readdir/read/write/mkdir/rename/unlink OK"
    )


def test_progress():
    # unit: formatting helpers
    assert host.middle_truncate("ABCDEFGHIJKL", 8) == "ABC...KL"
    line = host.progress_line("DOS\\PROG.EXE", 1000, 500, 2000)
    assert (
        len(line) == host.LINE_W and "PROG.EXE" in line and "%" in line and "[" in line
    )

    # agent: summary (newline-terminated) + a CR-overwriting live line per file
    dos, link, th = _boot()
    a = Path(tempfile.mktemp())
    a.write_bytes(b"A" * 500)
    b = Path(tempfile.mktemp())
    b.write_bytes(b"B" * 300)
    report = host.TransferReport()
    with contextlib.redirect_stdout(io.StringIO()):
        link.run_queue(
            [
                host._Job("up", a, "A.BIN", 500),
                host._Job("up", b, "B.BIN", 300),
            ],
            report,
            progress=False,
        )
    raw = bytes(dos.console)
    con = raw.decode("latin1")
    assert "Transfer:" in con, "remote summary header missing"
    assert "A.BIN" in con and "B.BIN" in con
    assert "%" in con, "progress bar percentage missing"
    assert b"\r" in raw, "live line did not use carriage-return overwrite"
    assert dos.fs["A.BIN"] == b"A" * 500 and dos.fs["B.BIN"] == b"B" * 300
    link.quit()
    th.join(timeout=5.0)
    print("  prog:    summary + CR-overwriting 80-col progress line on target")


def test_version_and_timestamps():
    """T_VERSION handshake and file date/time round-trip via ENTRY + GET/CLOSE."""
    # 2024-03-15 14:30:00 in FAT packed format
    fat_date = (44 << 9) | (3 << 5) | 15  # year 1980+44=2024, month 3, day 15
    fat_time = (14 << 11) | (30 << 5) | 0  # 14:30:00 (seconds/2 = 0)
    expected_epoch = host.fat_to_epoch(fat_date, fat_time)
    assert expected_epoch is not None

    dos, link, th = _boot(seed={"DATED.TXT": b"hello timestamps"})
    # _boot already called query_version(); assert it returned 1
    assert link.proto_version == 1, f"expected proto_version 1, got {link.proto_version}"
    dos.ftimes["DATED.TXT"] = (fat_time, fat_date)

    # list_dir should include time/date in ENTRY
    entries = link.list_dir("*.*")
    match = [e for e in entries if e[0] == "DATED.TXT"]
    assert match, f"DATED.TXT not in entries: {entries}"
    name, attr, size, mtime = match[0]
    assert mtime is not None, "mtime should be populated in v1 ENTRY"
    assert abs(mtime - expected_epoch) < 2, f"ENTRY mtime {mtime} != expected {expected_epoch}"

    # download: agent sends date in CLOSE; host should apply it to the local file
    dst = Path(tempfile.mktemp())
    link.download_file_once("DATED.TXT", dst)
    got_mtime = dst.stat().st_mtime
    assert abs(got_mtime - expected_epoch) < 2, (
        f"download mtime {got_mtime} != expected {expected_epoch}"
    )

    # upload: host sends date in CLOSE; agent should call do_setftime
    src = Path(tempfile.mktemp())
    src.write_bytes(b"upload with timestamp")
    import os as _os
    _os.utime(src, (expected_epoch, expected_epoch))
    link.upload_file_once(src, "UPPED.TXT")
    assert "UPPED.TXT" in dos.ftimes, "agent did not call do_setftime on upload"
    got_ft, got_fd = dos.ftimes["UPPED.TXT"]
    assert (got_fd, got_ft) == (fat_date, fat_time), (
        f"upload date/time mismatch: got ({got_fd:#x}, {got_ft:#x}), "
        f"expected ({fat_date:#x}, {fat_time:#x})"
    )

    link.quit()
    th.join(timeout=5.0)
    assert dos.exited == 0
    print(
        f"  timestamps: version=1, ENTRY date/time OK, download mtime applied, "
        f"upload setftime OK"
    )


def test_link_status_observer():
    """LinkStatus state-machine, byte-rate, and the Link observer hook."""
    import mountgui

    # --- state machine via observer callback ---
    s = mountgui.LinkStatus()
    assert s.state == "idle"

    s("ack")
    assert s.state == "ok"

    s("nak", "test NAK")
    assert s.state == "nak" and s.message == "test NAK"

    s("timeout")
    assert s.state == "no_reply"

    s("fail", "gave up")
    assert s.state == "error" and s.message == "gave up"

    s.set_ok("back")
    assert s.state == "ok" and s.message == "back"

    s.set_error("broke")
    assert s.state == "error"

    # --- byte-rate via add_bytes / speed_bps ---
    s.reset()
    assert s.state == "idle"
    s.add_bytes(1000)
    time.sleep(0.06)
    s.add_bytes(1000)
    assert s.speed_bps() > 0, "expected positive speed after two add_bytes calls"

    state, _msg, spd = s.snapshot()
    assert state == "idle"  # add_bytes does not change state
    assert spd > 0

    # --- Link observer integration: NAK then ACK ---
    events: list[str] = []

    def _obs(event: str, message: str = "") -> None:
        events.append(event)

    class _MockTransport:
        def __init__(self, responses: list[bytes]) -> None:
            self._resp = iter(responses)

        def send(self, data: bytes) -> None:
            pass

        def read_until(self, term: bytes, timeout: float = 5.0) -> bytes:
            try:
                return next(self._resp)
            except StopIteration:
                return b""  # simulates timeout

    nak_frame = host.make_frame(host.T_NAK, 0)
    ack_frame = host.make_frame(host.T_ACK, 0)
    link = host.Link(_MockTransport([nak_frame, ack_frame]), observer=_obs)
    result = link.xact(host.T_DATA)
    assert result == b""
    assert "nak" in events and "ack" in events
    assert events[-1] == "ack"

    # --- Link observer integration: all timeouts → fail ---
    events.clear()
    link2 = host.Link(_MockTransport([b"", b""]), retries=2, observer=_obs)
    try:
        link2.xact(host.T_DATA)
        raise AssertionError("should have raised OSError")
    except OSError:
        pass
    assert events.count("timeout") == 2
    assert "fail" in events

    print("  gui_obs: LinkStatus state-machine, speed, Link observer (NAK/ACK/timeout/fail) OK")


def test_size():
    assert len(COM) < 2800, f"COM unexpectedly large: {len(COM)} bytes"
    trailing_zeros = len(COM) - len(COM.rstrip(b"\x00"))
    assert trailing_zeros <= 1, (
        f"COM has {trailing_zeros} trailing zero bytes (BSS not stripped)"
    )
    print(f"  size:    XFER.COM is {len(COM)} bytes, no trailing BSS padding")


def main():
    print(f"XFER.COM built: {len(COM)} bytes  (crc16={SYM['crc16']:#x} main=0x100 ...)")
    test_codecs()
    test_framing()
    test_e2e()
    test_keyboard_quit()
    test_midstream_quit()
    test_dir_and_queue()
    test_v2()
    test_mountfs()
    test_progress()
    test_version_and_timestamps()
    test_link_status_observer()
    test_size()
    print("ALL TESTS PASS")


if __name__ == "__main__":
    main()
