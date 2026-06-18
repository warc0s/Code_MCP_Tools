import app as app_mod
from app import _resolve_host_binding


def test_resolve_host_binding_defaults(monkeypatch):
    monkeypatch.delenv("APP_HOST", raising=False)
    monkeypatch.setattr(app_mod, "_is_docker", lambda: False)
    host, display = _resolve_host_binding()
    assert host == "127.0.0.1"
    assert display == "127.0.0.1"


def test_resolve_host_binding_defaults_docker(monkeypatch):
    monkeypatch.delenv("APP_HOST", raising=False)
    monkeypatch.setattr(app_mod, "_is_docker", lambda: True)
    host, display = _resolve_host_binding()
    assert host == "0.0.0.0"
    assert display == "localhost"


def test_resolve_host_binding_custom_host(monkeypatch):
    monkeypatch.setenv("APP_HOST", "1.2.3.4")
    host, display = _resolve_host_binding()
    assert host == "1.2.3.4"
    assert display == "1.2.3.4"
