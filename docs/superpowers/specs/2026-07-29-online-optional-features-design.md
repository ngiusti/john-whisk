# Online-Optional Features — Design

Status: approved 2026-07-29. Keep John Whisk offline-first (the voice loop —
wake/STT/LLM/TTS — never needs internet), and add a few internet-backed
enhancements that fetch-when-online, cache locally, and degrade gracefully:
weather-aware suggestions, richer nutrition data (USDA), and a read-only iCal
calendar sync. Built in phases.

## Principles (non-negotiable)

1. **Never on the voice hot path.** Network calls are enhancements or background
   syncs — a voice turn never blocks for seconds on the internet.
2. **Cache to SQLite.** A feature that used the network once keeps working
   offline afterward.
3. **Degrade silently.** Short timeout; on offline / disabled / API error, fall
   back to local data or a brief "can't reach that right now." Never crash.
4. **Global off switch.** A single "online features" toggle disables all
   outbound calls.

## Foundation

### `john_whisk/settings.py` — runtime settings store
User-set values (secrets, URLs, location, toggles) live in the DB, editable from
the dashboard — not in code. `app_settings(key TEXT PRIMARY KEY, value TEXT)` in
`config.DB_PATH`. API: `get(key, default=None)`, `set(key, value)`,
`get_bool(key, default)`, `all()`.

### `john_whisk/net.py` — the online-optional helper
- `online()` -> bool (reads `settings` "online_enabled", default True).
- `get_json(url, params=None, timeout=8, headers=None)` -> dict | None.
- `get_text(url, timeout=10, headers=None)` -> str | None.
Both return None if online() is False, the request times out, errors, or the
network is down. Callers treat None as "no data, use the fallback."

### Dashboard — a Settings section "Online"
Toggle online features on/off; fields for **location** (city), **USDA FDC API
key**, and **iCal calendar URL**. All optional; a feature with no config simply
stays in its offline fallback.

## Feature 1 — Weather-aware suggestions (Open-Meteo, no key)

`john_whisk/weather.py`:
- Location: a city string in settings -> geocoded once via Open-Meteo's
  geocoding API -> lat/lon cached in settings.
- `current()` -> {temp_c, code, description} or None; cached in settings with a
  timestamp, refreshed at most ~hourly.
- `hint()` -> a short bias string ("It's cold out — something warm like a soup
  or stew would be good.") or "" when no data.
- Integration: `inventory.suggest` appends `weather.hint()` to its request so
  the LLM tailors ideas. Offline/disabled -> no hint, suggestions unchanged.

## Feature 2 — Richer nutrition (USDA FoodData Central)

Extend `nutrition.lookup`/`for_food`: on a LOCAL-seed miss, before the LLM
fallback, try `nutrition._fdc_lookup(food)`:
- `net.get_json("https://api.nal.usda.gov/fdc/v1/foods/search", {query, api_key,
  pageSize:1})`; api_key from settings (else skip).
- Parse per-100g calories/protein/carbs/fat from the top hit's `foodNutrients`.
- **Cache into `nutrition_foods`** (so it's local next time) and return it,
  `estimated=False`.
- On no key / offline / no hit -> fall through to the existing LLM estimate.

## Feature 3 — Read-only iCal calendar sync

`john_whisk/calsync.py`:
- iCal URL from settings. `sync()` -> `net.get_text(url)` -> parse VEVENTs
  (minimal hand-rolled parser: per VEVENT pull `DTSTART` date + `SUMMARY`; skip
  recurrence/timezone nuance in v1) -> replace the `ical_events` table
  (`id, event_date, description, uid, synced_at`). Returns count or None.
- **Lazy sync:** reading the look-ahead triggers a sync only if online and the
  last sync is stale (> ~1h); otherwise the cache is used. A "sync my calendar"
  voice/dashboard action forces it.
- Integration: `mealplan.upcoming` / `week_entries` merge `ical_events`
  alongside manual `events` (manual events untouched; a re-sync only replaces
  the iCal set). Offline -> last-cached events.

## Data flow

Voice/dashboard -> feature module -> `net` (if online) -> cache in SQLite ->
read from cache. All reads work from cache with no network.

## Error handling

- `net` returns None on any failure; every caller has a local fallback.
- Bad/missing settings (no key, no URL, no location) -> feature stays offline,
  no error to the user unless they explicitly invoke it ("I haven't got your
  calendar link yet — add it in settings").
- Malformed API payload -> treated as no data.

## Testing (TDD)

Network always mocked (monkeypatch `net.get_json` / `net.get_text`); deterministic.
- `settings`: get/set/round-trip, defaults, bool.
- `net`: returns None when online() False / on exception; parses on success.
- weather: geocode caching, `current()` cache freshness, `hint()` thresholds.
- nutrition FDC: parse a sample FDC payload -> macros; caches into
  nutrition_foods; no key -> skip to LLM fallback.
- calsync: parse sample ICS text -> events; `sync()` replaces the table; stale
  logic; merged into `mealplan.upcoming`.
- dashboard settings endpoints.

## Phasing

1. **Foundation:** `settings.py`, `net.py`, dashboard Online settings.
2. **Weather** (no key — fully testable/activatable immediately).
3. **Nutrition FDC** enrichment.
4. **iCal calendar** sync + merge into the look-ahead.

## Out of scope (now)

- Writing back to any calendar; OAuth; recurring-event expansion; multiple
  calendars; push notifications; any dependency beyond `requests` (ICS parsed
  by hand).

## Activation note

Each feature is built + tested with the network mocked, so it ships verifiable.
Real activation needs the user's inputs in Settings (location, FDC key, iCal
URL) and, obviously, internet — absent those, the feature stays in its offline
fallback.
