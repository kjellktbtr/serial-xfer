#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Build XFER.COM and launch it under DOSBox with COM1 on a TCP nullmodem socket
# (port 4555), so you can drive it from the host with --tcp 127.0.0.1:4555.
#
# Usage:   ./run_dosbox.sh
# Then, in a second terminal:
#   python3 host.py --tcp 127.0.0.1:4555 upload ./myfiles
#   python3 host.py --tcp 127.0.0.1:4555 download GOT.TXT ./got.txt
#   python3 host.py --tcp 127.0.0.1:4555 quit
#
# Set HEADLESS=1 to run without a window (SDL dummy video driver).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
nasm -f bin "$HERE/xfercom.asm" -o "$WORK/XFER.COM"
echo "Built $WORK/XFER.COM ($(stat -c%s "$WORK/XFER.COM") bytes)"

# DOSBox needs an 8.3 mount; generate a conf that mounts the build dir + runs it.
CONF="$WORK/dosbox-xfer.conf"
sed "s#@WORK@#$WORK#" "$HERE/dosbox-xfer.conf" > "$CONF"

if [ "${HEADLESS:-0}" = "1" ]; then
    export SDL_VIDEODRIVER=dummy
fi
echo "Launching DOSBox; COM1 -> TCP nullmodem 127.0.0.1:4555"
exec dosbox -conf "$CONF"
