from __future__ import annotations

import time


def add(left: int, right: int) -> int:
    return int(left) + int(right)


def make_unserializable():
    return object()


def slow(seconds: float = 0.5) -> str:
    time.sleep(float(seconds))
    return "ok"

