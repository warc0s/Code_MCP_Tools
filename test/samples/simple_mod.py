from __future__ import annotations

import time


def add(a, b):
    return a + b


class X:
    pass


def make_x():
    return X()


def slow():
    time.sleep(2)
    return "ok"

