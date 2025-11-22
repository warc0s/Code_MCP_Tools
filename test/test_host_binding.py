from app import _resolve_host_binding


def test_resolve_host_binding_defaults(monkeypatch):
    monkeypatch.delenv("APP_HOST", raising=False)
    host, display = _resolve_host_binding()
    assert host == "0.0.0.0"
    assert display == "localhost"


def test_resolve_host_binding_custom_host(monkeypatch):
    monkeypatch.setenv("APP_HOST", "1.2.3.4")
    host, display = _resolve_host_binding()
    assert host == "1.2.3.4"
    assert display == "1.2.3.4"
