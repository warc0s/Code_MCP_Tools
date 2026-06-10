from __future__ import annotations

import utils.cli_sessions as cli_sessions


class FakeSession:
    command = "python -u script.py"
    conda_env = None
    workdir = "."
    env = None
    batch_queries = None
    prompt_pattern = None

    def __init__(self):
        self.alive = True

    def is_alive(self):
        return self.alive


def test_restart_escalates_to_kill_before_starting(monkeypatch):
    session = FakeSession()
    cli_sessions.SESSIONS["restart-test"] = session
    stop_calls = []
    start_calls = []

    def fake_stop(session_id, kill=False, drop=True):
        stop_calls.append((session_id, kill, drop))
        if kill:
            session.alive = False
            return {"alive": False}
        return {"alive": True}

    def fake_start(**kwargs):
        start_calls.append(kwargs)
        return {"session_id": "new-session", "alive": True}

    monkeypatch.setattr(cli_sessions, "stop_session", fake_stop)
    monkeypatch.setattr(cli_sessions, "start_session", fake_start)

    result = cli_sessions.restart_session("restart-test")

    assert result["session_id"] == "new-session"
    assert stop_calls == [("restart-test", False, False), ("restart-test", True, False)]
    assert len(start_calls) == 1
    assert "restart-test" not in cli_sessions.SESSIONS


def test_restart_aborts_when_session_survives_kill(monkeypatch):
    session = FakeSession()
    cli_sessions.SESSIONS["restart-stuck"] = session
    start_calls = []

    def fake_stop(session_id, kill=False, drop=True):
        return {"alive": True}

    def fake_start(**kwargs):
        start_calls.append(kwargs)
        return {"session_id": "new-session", "alive": True}

    monkeypatch.setattr(cli_sessions, "stop_session", fake_stop)
    monkeypatch.setattr(cli_sessions, "start_session", fake_start)

    try:
        try:
            cli_sessions.restart_session("restart-stuck")
        except RuntimeError as exc:
            assert "Could not stop" in str(exc)
        else:
            raise AssertionError("restart_session should abort when the old process survives")
        assert start_calls == []
        assert "restart-stuck" in cli_sessions.SESSIONS
    finally:
        cli_sessions.SESSIONS.pop("restart-stuck", None)
