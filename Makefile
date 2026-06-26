# serial-xfer — build the DOS agent and run the test suite.
# SPDX-License-Identifier: GPL-2.0-only

.PHONY: all test lint format clean

all: XFER.COM

# Assemble the ~2 KB DOS agent (flat binary, no linker needed).
XFER.COM: xfercom.asm
	nasm -f bin $< -o $@

# Emulator-free regression suite (runs the COM under Unicorn). Needs the dev extra.
test:
	python3 test_com.py

lint:
	ruff check .

format:
	ruff format .

clean:
	rm -f XFER.COM
