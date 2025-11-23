#!/usr/bin/env python3
"""Emit chunks with small delays to simulate streaming."""
from __future__ import annotations

import sys
import time


def main() -> None:
    for i in range(10):
        sys.stdout.write(f"chunk {i}: " + ("." * (i + 1)) + "\n")
        sys.stdout.flush()
        time.sleep(0.3)
    print("done")


if __name__ == "__main__":
    main()

