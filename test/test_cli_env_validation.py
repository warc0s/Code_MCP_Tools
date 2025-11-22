from __future__ import annotations

import sys
from pathlib import Path as _Path
import pytest

# Ensure repository root in sys.path for local imports
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.cli_sessions import _validate_conda_env


@pytest.mark.parametrize(
    "name",
    [
        "base",
        "mcp",
        "code_tools",
        "env-01",
        "A_B-C",
    ],
)
def test_validate_conda_env_accepts_valid(name: str):
    assert _validate_conda_env(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        "  ",
        None,
    ],
)
def test_validate_conda_env_ignores_empty(name):
    assert _validate_conda_env(name) is None


@pytest.mark.parametrize(
    "name",
    [
        "my env",          # space
        "env;rm -rf /",    # shell symbol
        "env|echo x",      # pipe
        "env$(whoami)",    # subshell
        "a" * 65,           # too long
    ],
)
def test_validate_conda_env_rejects_invalid(name: str):
    with pytest.raises(ValueError) as ei:
        _validate_conda_env(name)
    msg = str(ei.value).lower()
    assert "invalid conda_env" in msg and ("letters" in msg or "letras" in msg)

