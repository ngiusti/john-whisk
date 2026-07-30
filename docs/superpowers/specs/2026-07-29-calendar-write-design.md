# Calendar Write (Google Calendar) — Design

Status: approved 2026-07-29. Let John Whisk CREATE events on the user's real
Google Calendar by voice ("add an appointment to my calendar August 20th at
4pm"). Read stays via the iCal cache; write needs the Google Calendar API with
OAuth. Offline-first still holds: writing needs the network at that moment, and
falls back to a local event when unreachable.

## Why this is different from read

The iCal `.ics` link is read-only — you cannot create events through it. Writing
requires the **Google Calendar API v3 with OAuth** (a Google Cloud project +
consent). This is the "full Google" path deferred earlier.

## One-time setup (user + a single consent)

1. User: create a free Google Cloud project, enable the Calendar API, configure
   an OAuth consent screen (External, add self as a test user), and create an
   **OAuth client of type "Desktop app"** -> download `credentials.json`.
2. Consent runs ONCE on a desktop browser (not the headless Pi): a local script
   opens the Google consent page; the user clicks Allow; a `token.json`
   (with a refresh token) is produced and copied to the Pi.
3. Thereafter the Pi refreshes the token silently — no re-login.

`credentials.json` and `token.json` live on the Pi at
`~/john-whisk/secrets/` and are **gitignored** (secrets, LAN-only).

## Dependencies (new)

`google-auth`, `google-auth-oauthlib`, `google-api-python-client` in the venv.
First non-`requests` network deps; installed on the Pi.

## Components

### `john_whisk/calwrite.py`
- `_service()` -> an authenticated Calendar API service, or None if not
  configured / token missing / refresh fails. Loads `token.json`, refreshes if
  expired (google-auth), builds `googleapiclient.discovery.build("calendar","v3")`.
  Import of google libs is lazy so the module (and tests) load without them.
- `available()` -> bool (token file present + online).
- `create_event(summary, start_dt, end_dt=None, all_day=False, tz=None)` ->
  a result dict {ok, link} or None. Builds the event body (all-day uses `date`;
  timed uses `dateTime` + timezone, default +1h if no end) and calls
  `service.events().insert(calendarId="primary", body=...).execute()`.

### Date + time parsing (`mealplan.py`)
Extend the existing date parser with time:
- `parse_time(text)` -> (hour, minute) or None: "4pm", "4:30pm", "16:00",
  "noon", "midnight", "at 4 in the afternoon/evening/morning".
- `parse_datetime(text, now)` -> (date, time_or_None) reusing `parse_date`.

### Router intent (`router.py`)
`calendar_add` — "add an appointment", "to my calendar", "on my google calendar",
"create an event", "schedule an appointment". Checked BEFORE `calendar_query`
(read) and `event_add` (local) so a write phrasing wins. "what's on my calendar"
(read) and "I have plans Friday" (local) are unaffected.

### Handler (`mealplan.handle_calendar_add`)
Parse date + time + summary. If `calwrite.available()`: create the Google event
(timed = 1h default; no time = all-day), confirm, and trigger `calsync.sync()`
so it appears in the local look-ahead. Else fall back to a LOCAL event and say
it was saved locally / Google was unreachable.

### Main dispatch
Route `calendar_add` -> `mealplan.handle_calendar_add`.

## Offline / failure behavior

- No token / not set up -> "I can't add to your Google calendar yet — set it up
  in settings." (or fall back to a local event, configurable; default: local
  event + note).
- Offline / API error -> save a local event and say it'll need re-adding when
  online, or report the failure. Never crash.

## Testing (TDD)

Google libs + network mocked; deterministic.
- `parse_time`: pm/am, :30, 24h, noon/midnight, none.
- `parse_datetime`: date + time combined.
- `calwrite.create_event`: with a fake service, asserts the correct body
  (all-day vs timed, default +1h) and that insert().execute() is called;
  `_service()` None -> create_event returns None.
- router: `calendar_add` classified; not shadowing read/local/event intents.
- handler: with `calwrite.available()` True (mocked) creates + confirms; False
  falls back to a local event.

## Out of scope (now)

- Editing/deleting Google events; multiple calendars; recurring events;
  attendees/reminders; timezone selection UI (uses the Pi/lat-lon default).
