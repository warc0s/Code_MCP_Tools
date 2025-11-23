#!/usr/bin/env python3
"""Emit many lines quickly."""
from __future__ import annotations

import sys


def main() -> None:
    for i in range(1000):
        sys.stdout.write(f"line {i}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()

