#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 Kjell Kristian Grane Torgersen
"""Tkinter GUI for mountfs.py.

Launched automatically when ``python mountfs.py`` is run with no arguments.
Serial connection only; --socket/--tcp emulator paths stay CLI-only.

The tkinter import lives inside build_and_run() so the module can be imported
headlessly (e.g. in test_com.py) without a display.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

_BAUD_CHOICES = [2400, 4800, 9600, 19200, 38400, 57600, 115200]
_DEFAULT_BAUD = 9600
_DEFAULT_ROOT = "C:\\"

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


# ---------------------------------------------------------------------------
# Thread-safe status + byte-rate tracker  (no Tk dependency — unit-testable)
# ---------------------------------------------------------------------------
class LinkStatus:
    """Thread-safe status shared between the mount worker thread and the GUI.

    Doubles as the ``observer`` callback for ``host.Link`` — call signature is
    ``status(event, message="")`` where *event* is one of
    ``"ack" | "nak" | "timeout" | "fail"``.

    Also used directly (``set_ok`` / ``set_error``) by the mount thread for
    coarser state changes (connecting, crawling, unmounted, …).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state: str = "idle"   # "idle" | "ok" | "nak" | "no_reply" | "error"
        self.message: str = ""
        self._samples: deque[tuple[float, int]] = deque()  # (monotonic, nbytes)

    def __call__(self, event: str, message: str = "") -> None:
        """Link observer callback; called from the mount thread."""
        with self._lock:
            if event == "ack":
                self.state = "ok"
                self.message = message or "OK"
            elif event == "nak":
                self.state = "nak"
                self.message = message or "NAK — retrying"
            elif event == "timeout":
                self.state = "no_reply"
                self.message = message or "No reply — retrying"
            elif event == "fail":
                self.state = "error"
                self.message = message or "Failed"

    def set_error(self, msg: str) -> None:
        with self._lock:
            self.state = "error"
            self.message = msg

    def set_ok(self, msg: str) -> None:
        with self._lock:
            self.state = "ok"
            self.message = msg

    def add_bytes(self, n: int) -> None:
        """Record *n* wire bytes for the rolling-window speed calculation."""
        t = time.monotonic()
        with self._lock:
            self._samples.append((t, n))
            cutoff = t - 2.0
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.popleft()

    def _speed_bps_locked(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        total = sum(s[1] for s in self._samples)
        window = self._samples[-1][0] - self._samples[0][0]
        return total / window if window > 0 else 0.0

    def speed_bps(self) -> float:
        """Bytes/second over the last ~2 s (thread-safe)."""
        with self._lock:
            return self._speed_bps_locked()

    def snapshot(self) -> tuple[str, str, float]:
        """Atomically return ``(state, message, speed_bps)``."""
        with self._lock:
            return self.state, self.message, self._speed_bps_locked()

    def reset(self) -> None:
        with self._lock:
            self.state = "idle"
            self.message = ""
            self._samples.clear()


# ---------------------------------------------------------------------------
# Byte-counting transport wrapper  (no Tk dependency)
# ---------------------------------------------------------------------------
class _MonitoredTransport:
    """Wraps any Transport, counting all wire bytes into a ``LinkStatus``."""

    def __init__(self, inner: object, status: LinkStatus) -> None:
        self._inner = inner
        self._status = status

    def send(self, data: bytes) -> None:
        self._inner.send(data)  # type: ignore[attr-defined]
        self._status.add_bytes(len(data))

    def read_until(self, term: bytes, timeout: float = 5.0) -> bytes:
        data: bytes = self._inner.read_until(term, timeout)  # type: ignore[attr-defined]
        self._status.add_bytes(len(data))
        return data


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------
def list_serial_ports() -> list[str]:
    """Return available serial port device names; empty list if pyserial absent."""
    try:
        import serial.tools.list_ports
        return [p.device for p in serial.tools.list_ports.comports()]
    except ImportError:
        return []


def free_drive_letters() -> list[str]:
    """Windows only: drive letters D: onwards that are not currently in use."""
    import string
    try:
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
        used = {chr(ord("A") + i) for i in range(26) if bitmask & (1 << i)}
    except Exception:
        used = set("ABCDE")  # safe fallback
    return [f"{c}:" for c in string.ascii_uppercase[3:] if c not in used]


def unmount(mountpoint: str) -> None:
    """Best-effort unmount.  FUSE's destroy() callback already calls link.quit().

    On Windows the FUSE thread unwinds when WinFsp releases the drive letter
    (e.g. via the WinFsp system-tray icon or ``net use X: /delete``).  There is
    no reliable cross-version Python API to trigger that from here, so this
    function is a no-op on Windows.  Untested on a real Windows machine.
    """
    if sys.platform == "win32":
        return
    for cmd in (["fusermount", "-u", mountpoint], ["umount", mountpoint]):
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            if result.returncode == 0:
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
def build_and_run() -> None:
    """Build and show the mount control window; blocks until the window closes."""
    import tkinter as tk
    from tkinter import filedialog, ttk

    import mountfs
    from host import Link, SerialTransport

    status = LinkStatus()
    mount_thread: threading.Thread | None = None
    _mp_box: list[str] = [""]       # current mountpoint (mutable closure cell)
    _closing: list[bool] = [False]  # True = window-close requested while mounted

    # ------------------------------------------------------------------ window
    root = tk.Tk()
    root.title("serial-xfer mount")
    root.resizable(False, False)

    pad: dict = {"padx": 6, "pady": 3}
    frame = ttk.Frame(root, padding=12)
    frame.grid(sticky="nsew")

    row = 0

    # --- Serial port ---
    ttk.Label(frame, text="Serial port:").grid(row=row, column=0, sticky="w", **pad)
    port_var = tk.StringVar()
    port_cb = ttk.Combobox(frame, textvariable=port_var, width=24)
    port_cb.grid(row=row, column=1, sticky="ew", **pad)

    def _refresh_ports() -> None:
        ports = list_serial_ports()
        port_cb["values"] = ports
        if ports and not port_var.get():
            port_var.set(ports[0])

    _refresh_ports()
    ttk.Button(frame, text="⟳", width=3, command=_refresh_ports).grid(
        row=row, column=2, padx=(0, 6)
    )
    row += 1

    # --- Baud rate ---
    ttk.Label(frame, text="Baud rate:").grid(row=row, column=0, sticky="w", **pad)
    baud_var = tk.StringVar(value=str(_DEFAULT_BAUD))
    baud_cb = ttk.Combobox(
        frame, textvariable=baud_var,
        values=[str(b) for b in _BAUD_CHOICES], width=24,
    )
    baud_cb.grid(row=row, column=1, sticky="ew", **pad)
    row += 1

    # --- Remote root ---
    ttk.Label(frame, text="Remote root:").grid(row=row, column=0, sticky="w", **pad)
    root_var = tk.StringVar(value=_DEFAULT_ROOT)
    root_entry = ttk.Entry(frame, textvariable=root_var, width=26)
    root_entry.grid(row=row, column=1, sticky="ew", **pad)
    row += 1

    # --- Mount target ---
    ttk.Label(frame, text="Mount at:").grid(row=row, column=0, sticky="w", **pad)
    mp_var = tk.StringVar()
    mp_input: tk.Widget
    if sys.platform == "win32":
        mp_input = ttk.Combobox(frame, textvariable=mp_var, width=24)
        letters = free_drive_letters()
        mp_input["values"] = letters  # type: ignore[index]
        if letters:
            mp_var.set(letters[0])
        mp_input.grid(row=row, column=1, sticky="ew", **pad)
    else:
        mp_input = ttk.Entry(frame, textvariable=mp_var, width=24)
        mp_input.grid(row=row, column=1, sticky="ew", **pad)

        def _browse_mp() -> None:
            d = filedialog.askdirectory(title="Choose mount directory")
            if d:
                mp_var.set(d)

        ttk.Button(frame, text="…", width=3, command=_browse_mp).grid(
            row=row, column=2, padx=(0, 6)
        )
    row += 1

    # --- Separator ---
    ttk.Separator(frame, orient="horizontal").grid(
        row=row, column=0, columnspan=3, sticky="ew", pady=6
    )
    row += 1

    # --- Status label ---
    status_var = tk.StringVar(value="Idle")
    status_label = ttk.Label(frame, textvariable=status_var, width=42, anchor="w")
    status_label.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 6))
    row += 1

    # --- Buttons ---
    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=row, column=0, columnspan=3, sticky="e")
    mount_btn = ttk.Button(btn_frame, text="Mount", width=10)
    mount_btn.grid(row=0, column=0, padx=(0, 4))
    close_btn = ttk.Button(btn_frame, text="Close", width=10)
    close_btn.grid(row=0, column=1)

    _all_inputs = [port_cb, baud_cb, root_entry, mp_input]

    def _set_inputs_state(state: str) -> None:
        for w in _all_inputs:
            w.configure(state=state)

    # ------------------------------------------------------------------ logic
    def _poll() -> None:
        nonlocal mount_thread
        st, message, speed = status.snapshot()

        color_map = {
            "ok": "green",
            "nak": "#cc8800",
            "no_reply": "#cc8800",
            "error": "red",
        }
        color = color_map.get(st, "")

        spd_str = ""
        if speed > 50:
            spd_str = f" • {speed / 1024:.1f} KB/s"

        status_var.set((message or "Idle") + spd_str)
        status_label.configure(foreground=color)

        if mount_thread is not None and not mount_thread.is_alive():
            mount_thread = None
            _set_inputs_state("normal")
            mount_btn.configure(text="Mount", command=_do_mount, state="normal")
            if _closing[0]:
                root.destroy()
                return

        root.after(200, _poll)

    def _do_mount() -> None:
        nonlocal mount_thread
        port = port_var.get().strip()
        if not port:
            status_var.set("No serial port selected")
            status_label.configure(foreground="red")
            return
        try:
            baud = int(baud_var.get().strip())
        except ValueError:
            status_var.set("Invalid baud rate")
            status_label.configure(foreground="red")
            return
        mp = mp_var.get().strip()
        if not mp:
            status_var.set("No mount point specified")
            status_label.configure(foreground="red")
            return
        dos_root = root_var.get().strip() or _DEFAULT_ROOT

        _mp_box[0] = mp
        status.reset()
        _set_inputs_state("disabled")
        mount_btn.configure(text="Unmount", command=_do_unmount)
        status_var.set("Connecting…")
        status_label.configure(foreground="")

        def _worker() -> None:
            try:
                transport = SerialTransport(port, baud)
                monitored = _MonitoredTransport(transport, status)
                link = Link(monitored, observer=status)
                status.set_ok("Connected — querying version…")
                link.query_version()
                status.set_ok("Crawling root directory…")
                rfs = mountfs.RemoteFS(link, dos_root)
                rfs.start()
                status.set_ok("Mounted")

                try:
                    from fuse import FUSE
                except ImportError:
                    from winfsp.fuse import FUSE  # type: ignore[no-redef]

                # Blocks until unmounted (fusermount -u on Linux; WinFsp tray on Windows).
                # destroy() callback in mountfs._build_fuse_ops sends T_QUIT to the agent.
                FUSE(mountfs._build_fuse_ops(rfs), mp, foreground=True, nothreads=False)
                status.set_ok("Unmounted")
            except Exception as e:
                status.set_error(str(e))

        mount_thread = threading.Thread(target=_worker, daemon=True, name="mount-worker")
        mount_thread.start()

    def _do_unmount() -> None:
        mp = _mp_box[0]
        if mp:
            unmount(mp)
        # The mount thread unblocks when FUSE returns → _poll() re-enables inputs.

    def _on_close() -> None:
        if mount_thread is not None and mount_thread.is_alive():
            _closing[0] = True
            _do_unmount()
            # _poll() calls root.destroy() once the thread has finished.
        else:
            root.destroy()

    mount_btn.configure(command=_do_mount)
    close_btn.configure(command=_on_close)
    root.protocol("WM_DELETE_WINDOW", _on_close)

    root.after(200, _poll)
    root.mainloop()
