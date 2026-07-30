"""Online-optional network helper. Every call returns None when online features
are switched off, the request times out, or anything errors — so callers always
fall back to local data and the internet stays strictly optional."""
import requests

from john_whisk import settings

_UA = {"User-Agent": "JohnWhisk/1.0 (offline-first kitchen assistant)"}


def online():
    """Whether outbound calls are allowed (global toggle, default on)."""
    return settings.get_bool("online_enabled", True)


def get_json(url, params=None, timeout=8, headers=None):
    """GET JSON, or None if offline/disabled/timeout/error/bad payload."""
    if not online():
        return None
    try:
        r = requests.get(url, params=params, timeout=timeout, headers=headers or _UA)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def get_text(url, timeout=10, headers=None):
    """GET text, or None if offline/disabled/timeout/error."""
    if not online():
        return None
    try:
        r = requests.get(url, timeout=timeout, headers=headers or _UA)
        r.raise_for_status()
        return r.text
    except requests.RequestException:
        return None
