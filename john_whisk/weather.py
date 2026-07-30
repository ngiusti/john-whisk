"""Weather-aware suggestion bias via Open-Meteo (free, no API key). Geocodes the
configured city once, caches current conditions ~hourly, and offers a short hint
to nudge suggestions. Fully optional: no location / offline -> empty hint."""
import datetime
import json
import re

from john_whisk import net, settings

_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST = "https://api.open-meteo.com/v1/forecast"
_FRESH_S = 3600           # refresh current conditions at most hourly
_COLD_C = 5
_HOT_C = 28


def _latlon():
    """(lat, lon) for the configured location, geocoded once and cached. Handles
    "City State" ("aloha oregon") by searching the city and disambiguating on the
    remaining words against the result's state/country. None if unresolved."""
    raw = (settings.get("location") or "").strip()
    if not raw:
        return None
    if settings.get("geo_city") == raw and settings.get("lat") and settings.get("lon"):
        return float(settings.get("lat")), float(settings.get("lon"))
    parts = [p for p in re.split(r"[,\s]+", raw) if p]
    name = parts[0]
    hint = " ".join(parts[1:]).lower()          # e.g. "oregon"
    data = net.get_json(_GEOCODE, {"name": name, "count": 10})
    res = (data or {}).get("results") or []
    if not res:
        return None
    chosen = res[0]
    if hint:
        for r in res:
            admin = (r.get("admin1") or "").lower()
            country = (r.get("country") or "").lower()
            cc = (r.get("country_code") or "").lower()
            if (len(hint) >= 3 and (hint in admin or hint in country)) or hint == cc:
                chosen = r
                break
    lat, lon = float(chosen["latitude"]), float(chosen["longitude"])
    settings.set("lat", lat)
    settings.set("lon", lon)
    settings.set("geo_city", raw)
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
