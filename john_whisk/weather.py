"""Weather-aware suggestion bias via Open-Meteo (free, no API key). Geocodes the
configured city once, caches current conditions ~hourly, and offers a short hint
to nudge suggestions. Fully optional: no location / offline -> empty hint."""
import datetime
import json

from john_whisk import net, settings

_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST = "https://api.open-meteo.com/v1/forecast"
_FRESH_S = 3600           # refresh current conditions at most hourly
_COLD_C = 5
_HOT_C = 28


def _latlon():
    """(lat, lon) for the configured city, geocoded once and cached. None if no
    city set or geocoding unavailable."""
    city = (settings.get("location") or "").strip()
    if not city:
        return None
    if settings.get("geo_city") == city and settings.get("lat") and settings.get("lon"):
        return float(settings.get("lat")), float(settings.get("lon"))
    data = net.get_json(_GEOCODE, {"name": city, "count": 1})
    res = (data or {}).get("results") or []
    if not res:
        return None
    lat, lon = float(res[0]["latitude"]), float(res[0]["longitude"])
    settings.set("lat", lat)
    settings.set("lon", lon)
    settings.set("geo_city", city)
    return lat, lon


def current(now=None):
    """Cached current weather {temp_c, code}, refreshed ~hourly. Returns the last
    cache (or None) when offline/unavailable."""
    now = now or datetime.datetime.now()
    cached = settings.get("weather_json")
    ts = settings.get("weather_ts")
    if cached and ts:
        try:
            if (now - datetime.datetime.fromisoformat(ts)).total_seconds() < _FRESH_S:
                return json.loads(cached)
        except (ValueError, TypeError):
            pass
    ll = _latlon()
    if not ll:
        return json.loads(cached) if cached else None
    data = net.get_json(_FORECAST, {"latitude": ll[0], "longitude": ll[1],
                                    "current": "temperature_2m,weather_code"})
    cur = (data or {}).get("current") if data else None
    if not cur:
        return json.loads(cached) if cached else None
    out = {"temp_c": cur.get("temperature_2m"), "code": cur.get("weather_code")}
    settings.set("weather_json", json.dumps(out))
    settings.set("weather_ts", now.isoformat(timespec="seconds"))
    return out


def hint(now=None):
    """A short suggestion-bias phrase for the weather, or "" when unavailable
    or mild."""
    c = current(now)
    if not c or c.get("temp_c") is None:
        return ""
    t = c["temp_c"]
    if t <= _COLD_C:
        return ("It's cold out, so something warm and hearty like a soup, stew, "
                "or bake would be great.")
    if t >= _HOT_C:
        return ("It's hot out, so something light or no-cook like a salad, or "
                "something grilled, would be nice.")
    return ""
