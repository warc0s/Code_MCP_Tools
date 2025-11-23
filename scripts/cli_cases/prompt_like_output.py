#!/usr/bin/env python3
"""Print lines that resemble prompts but are not asking for input."""
from __future__ import annotations

def main() -> None:
    samples = [
        "status> ok",
        "question? actually just a line",
        "path: /var/log/app",
        "ready> still not awaiting input",
    ]
    for s in samples:
        print(s)
    print("bye")


if __name__ == "__main__":
    main()

