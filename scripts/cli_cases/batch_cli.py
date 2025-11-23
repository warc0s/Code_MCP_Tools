#!/usr/bin/env python3
"""Read lines from stdin and echo them until 'quit'."""
from __future__ import annotations

import sys


def main() -> None:
    print("Send lines; type 'quit' to exit.")
    for line in sys.stdin:
        text = line.strip()
        print(f"got: {text}")
        sys.stdout.flush()
        if text.lower() == "quit":
            print("bye")
            sys.stdout.flush()
            break


if __name__ == "__main__":
    main()

