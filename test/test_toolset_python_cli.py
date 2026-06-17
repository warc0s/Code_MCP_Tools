from __future__ import annotations

import sys
from pathlib import Path as _Path

import pytest

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from mcp_server.toolset import RAGToolset


def test_build_python_command_module_repl_includes_i_flag():
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    cmd = ts._build_python_command({
        "mode": "module_repl",
        "module_name": "test",
        "args": ["--help"],
        "python_opts": {"unbuffered": True},
    })
    # Should include -i -m test in quoted command
    assert "-i -m test" in cmd


def test_build_python_command_script_error_messages_are_informative(tmp_path):
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    # Absolute path outside repo should be rejected with detailed message
    fake_abs = "/tmp/not_here.py"
    with pytest.raises(ValueError) as ei:
        ts._build_python_command({
            "mode": "script",
            "script_path": fake_abs,
            "python_opts": {"unbuffered": True},
        })
    msg = str(ei.value)
    assert "repo_root=" in msg and "resolved=" in msg


def test_build_python_command_rejects_prefix_confusion_workdir(tmp_path, monkeypatch):
    repo_root = tmp_path / "Contextarium"
    evil_root = tmp_path / "Contextarium_evil"
    repo_root.mkdir(parents=True, exist_ok=True)
    evil_root.mkdir(parents=True, exist_ok=True)
    (evil_root / "ok.py").write_text("print('hello')\n", encoding="utf-8")

    monkeypatch.chdir(repo_root)

    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    with pytest.raises(ValueError) as ei:
        ts._build_python_command({
            "mode": "script",
            "workdir": "../Contextarium_evil",
            "script_path": "ok.py",
            "python_opts": {"unbuffered": True},
        })
    assert "Workdir outside repository" in str(ei.value)
