"""Weather-aware suggestions (Open-Meteo). Network mocked; DB isolated."""
import datetime

from john_whisk import config, settings, weather

NOW = datetime.datetime(2026, 7, 15, 12, 0, 0)


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))
    settings.set("online_enabled", "1")


def test_latlon_geocodes_and_caches(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    settings.set("location", "Denver")
    calls = {"n": 0}

    def fake(url, params=None, **k):
        calls["n"] += 1
        return {"results": [{"latitude": 39.7, "longitude": -105.0}]}

    monkeypatch.setattr(weather.net, "get_json", fake)
    assert weather._latlon() == (39.7, -105.0)
    weather._latlon()                       # second call hits the cache
    assert calls["n"] == 1


def test_current_caches_and_is_fresh(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    settings.set("location", "Denver")
    settings.set("geo_city", "Denver")
    settings.set("lat", "39.7")
    settings.set("lon", "-105.0")
    monkeypatch.setattr(weather.net, "get_json",
                        lambda *a, **k: {"current": {"temperature_2m": 2.0, "weather_code": 71}})
    assert weather.current(NOW)["temp_c"] == 2.0


def test_hint_cold_hot_mild(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(weather, "current", lambda now=None: {"temp_c": 1.0, "code": 0})
    assert "warm" in weather.hint().lower() or "soup" in weather.hint().lower()
    monkeypatch.setattr(weather, "current", lambda now=None: {"temp_c": 32.0, "code": 0})
    assert "light" in weather.hint().lower() or "salad" in weather.hint().lower()
    monkeypatch.setattr(weather, "current", lambda now=None: {"temp_c": 18.0, "code": 0})
    assert weather.hint() == ""


def test_hint_no_data_is_empty(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(weather, "current", lambda now=None: None)
    assert weather.hint() == ""
