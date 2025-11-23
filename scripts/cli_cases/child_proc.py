#!/usr/bin/env python3
"""Spawn a child process that sleeps, then report."""
from __future__ import annotations

import subprocess
import sys
import time


def main() -> None:
    print("parent: starting child...")
    # Spawn a child that sleeps; -u for unbuffered
    code = "import time,sys; print('child: sleeping'); sys.stdout.flush(); time.sleep(10); print('child: done'); sys.stdout.flush()"
    p = subprocess.Popen([sys.executable, "-u", "-c", code])
    print(f"parent: child pid={p.pid}")
    sys.stdout.flush()
    try:
        for i in range(5):
            print(f"parent: tick {i}")
            sys.stdout.flush()
            time.sleep(1.0)
    finally:
        print("parent: exiting main loop")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

