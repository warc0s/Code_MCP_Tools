from __future__ import annotations

import sys
from pathlib import Path as _Path

import pytest

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from mcp_server.toolset import RAGToolset


def test_call_function_success_json_result():
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    res = ts.call(
        "python_call_function",
        {
            "module": "test.samples.simple_mod",
            "function": "add",
            "args": [2, 3],
            "timeout_ms": 1000,
        },
    )
    assert res.get("ok") is True
    assert res.get("result") == 5


def test_call_function_unserializable_result():
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    res = ts.call(
        "python_call_function",
        {
            "module": "test.samples.simple_mod",
            "function": "make_x",
            "timeout_ms": 1000,
        },
    )
    assert res.get("ok") is False
    assert res.get("error_type") == "ResultNotSerializable"


def test_call_function_timeout():
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    res = ts.call(
        "python_call_function",
        {
            "module": "test.samples.simple_mod",
            "function": "slow",
            "timeout_ms": 100,
        },
    )
    assert res.get("ok") is False
    assert res.get("error_type") in {"Timeout"}

