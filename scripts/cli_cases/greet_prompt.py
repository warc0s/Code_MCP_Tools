#!/usr/bin/env python3
"""Simple prompt then exit.

Prints a prompt without newline, reads a name and greets, then exits.
"""
from __future__ import annotations

import sys


def main() -> None:
    sys.stdout.write("Enter your name: ")
    sys.stdout.flush()
    try:
        name = input().strip()
    except EOFError:
        print("\nEOF received. Exiting.")
        return
    if not name:
        name = "anonymous"
    print(f"Hello, {name}! Bye.")


if __name__ == "__main__":
    main()

