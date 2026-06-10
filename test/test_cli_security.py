from __future__ import annotations

from pathlib import Path

import pytest

from utils.cli_sessions import start_session


def test_start_session_rejects_python_script_outside_repo(tmp_path):
    external = tmp_path / "outside.py"
    external.write_text("print('outside')\n", encoding="utf-8")

    with pytest.raises(ValueError, match="outside repository"):
        start_session(
            command=f"python -u {external}",
            timeout=0.05,
            max_bytes=1024,
            log_enabled=False,
        )


def test_start_session_rejects_workdir_outside_repo(tmp_path):
    with pytest.raises(ValueError, match="workdir outside repository"):
        start_session(
            command="python -u -c 'print(1)'",
            workdir=str(tmp_path),
            timeout=0.05,
            max_bytes=1024,
            log_enabled=False,
        )

