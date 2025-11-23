#!/usr/bin/env python3
"""Sleep without producing output, then print a final line."""
from __future__ import annotations

import time


def main() -> None:
    time.sleep(2.0)
    print("done")


if __name__ == "__main__":
    main()

