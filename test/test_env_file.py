from __future__ import annotations

import logging

import utils.env as env_mod


def test_load_env_file_logs_read_errors(monkeypatch, caplog, tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=test\n", encoding="utf-8")

    def fail_read_text(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(env_mod.Path, "read_text", fail_read_text)

    with caplog.at_level(logging.WARNING, logger="utils.env"):
        env_mod.load_env_file(env_path)

    assert "Could not read env file" in caplog.text
    assert "permission denied" in caplog.text
