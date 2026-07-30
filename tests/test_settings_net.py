"""Foundation: runtime settings store + the online-optional net helper.
Network is always mocked; DB isolated."""
from john_whisk import config, settings, net


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))


def test_settings_roundtrip_and_default(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert settings.get("location", "none") == "none"
    settings.set("location", "Denver")
    assert settings.get("location") == "Denver"


def test_settings_bool_default_and_set(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert settings.get_bool("online_enabled", True) is True
    settings.set("online_enabled", "0")
    assert settings.get_bool("online_enabled", True) is False


class _Resp:
    def __init__(self, payload=None, text="", exc=False):
        self._payload = payload
        self.text = text
        self._exc = exc

    def raise_for_status(self):
        if self._exc:
            raise net.requests.RequestException("boom")

    def json(self):
        return self._payload


def test_net_returns_none_when_offline(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    settings.set("online_enabled", "0")
    monkeypatch.setattr(net.requests, "get", lambda *a, **k: _Resp({"x": 1}))
    assert net.get_json("http://example.com") is None      # disabled -> no result


def test_net_get_json_success(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    settings.set("online_enabled", "1")
    monkeypatch.setattr(net.requests, "get", lambda *a, **k: _Resp(payload={"ok": True}))
    assert net.get_json("http://example.com") == {"ok": True}


def test_net_get_json_error_returns_none(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    settings.set("online_enabled", "1")
    monkeypatch.setattr(net.requests, "get", lambda *a, **k: _Resp(exc=True))
    assert net.get_json("http://example.com") is None


def test_net_get_text_success(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    settings.set("online_enabled", "1")
    monkeypatch.setattr(net.requests, "get", lambda *a, **k: _Resp(text="hello"))
    assert net.get_text("http://example.com") == "hello"
