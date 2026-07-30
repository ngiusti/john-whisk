"""Write events to Google Calendar (API v3, OAuth). Reading stays via the iCal
cache; this CREATES events. The google-* libs and the OAuth token are loaded
lazily, so the module imports fine without them and tests mock `_service()`."""
import datetime
import os

from john_whisk import config, net

_SECRETS = os.path.join(config.HOME, "john-whisk", "secrets")
_TOKEN = os.path.join(_SECRETS, "token.json")
_CREDS = os.path.join(_SECRETS, "credentials.json")
_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
_DEFAULT_TZ = "America/Los_Angeles"       # Pacific; matches the configured city


def _tz():
    from john_whisk import settings
    return settings.get("timezone") or _DEFAULT_TZ


def _service():
    """An authenticated Calendar service, or None if not set up / token bad.
    Refreshes an expired token silently."""
    if not os.path.exists(_TOKEN):
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        creds = Credentials.from_authorized_user_file(_TOKEN, _SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(_TOKEN, "w") as f:
                    f.write(creds.to_json())
            else:
                return None
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        return None


def available():
    """True if online and an OAuth token is present."""
    return net.online() and os.path.exists(_TOKEN)


def create_event(summary, start, end=None, all_day=False, tz=None):
    """Create an event on the primary calendar. `start`/`end` are date (all-day)
    or datetime (timed; end defaults to +1h). Returns {ok, link} or None."""
    svc = _service()
    if svc is None:
        return None
    if all_day:
        body = {"summary": summary,
                "start": {"date": start.isoformat()},
                "end": {"date": (start + datetime.timedelta(days=1)).isoformat()}}
    else:
        end = end or (start + datetime.timedelta(hours=1))
        zone = tz or _tz()
        body = {"summary": summary,
                "start": {"dateTime": start.isoformat(), "timeZone": zone},
                "end": {"dateTime": end.isoformat(), "timeZone": zone}}
    try:
        ev = svc.events().insert(calendarId="primary", body=body).execute()
        return {"ok": True, "link": ev.get("htmlLink", "")}
    except Exception:
        return None
