# Phone / Web Dashboard — Design

Status: approved 2026-07-28. A mobile web hub served from the Pi so the household
can view + edit the kitchen state from a phone on the home network. The "reach
beyond voice" North Star, v1 = full editable hub.

## Decisions (from brainstorming)

- **Flask** on the Pi (no front-end build step: mobile HTML/CSS/vanilla JS).
- **Second systemd service** (`john-whisk-web.service`), **LAN-only**, no external
  exposure, no auth in v1 (home network).
- **One source of truth**: the web app imports and reuses the existing store
  modules — same SQLite databases as the voice app, so edits sync both ways.
- v1 sections, all editable: **grocery, pantry, recipes (browse/search), settings
  (dietary / equipment / flavor / ratings)**.

## Architecture

### `john_whisk/web.py` — Flask app
`create_app()` builds the app (so tests can use `app.test_client()`); a
`__main__` block runs it. Reuses `db`/`inventory`, `grocery`, `recipes`,
`ratings`, `restrictions`, `equipment`, `flavor` — NO duplicated logic. The
single-page HTML/CSS/JS is embedded as a string constant (one file, no template
dir needed on the Pi).

### Config — `john_whisk/config.py`
`WEB_HOST = "0.0.0.0"` (LAN), `WEB_PORT = 8080`.

### JSON API (all return/accept JSON)
- Grocery: `GET /api/grocery` -> {items:[...]}; `POST /api/grocery` {item} -> add;
  `POST /api/grocery/remove` {item} -> check off/remove; `POST /api/grocery/clear`.
- Pantry: `GET /api/pantry` -> {items:[{name,quantity,unit,category}]};
  `POST /api/pantry` {name} -> add; `POST /api/pantry/remove` {name} -> remove.
- Recipes: `GET /api/recipes?q=<query>` -> {results:[{title}]} (search or, empty
  q, a sample + count); `GET /api/recipes/view?title=<t>` -> {title,ingredients,
  steps}.
- Settings: `GET /api/settings` -> {restrictions, equipment, flavor, favorites,
  disliked}; `POST /api/restrictions|equipment|flavor` {item} -> add;
  `POST /api/.../remove` {item} -> remove.
(POST bodies as JSON; add/remove reuse the modules' set_from_text-free direct
functions — e.g. `restrictions.add([canonical])`, `equipment.add`, `grocery.add`,
`db.add_items`, `db.remove_items`.)

### Page (`GET /`)
A mobile-first single page: a top tab bar (Grocery / Pantry / Recipes / Settings)
and a panel per tab. Vanilla JS `fetch()`es the API and re-renders. Grocery items
have a checkbox that removes them (shopping flow); pantry/settings have add fields
and remove buttons; recipes has a search box + list, tapping a title shows its
ingredients + steps. Plain readable CSS, large tap targets, no external CDNs
(offline-friendly).

### Deployment
- `/etc/systemd/system/john-whisk-web.service`: `User=ngiusti`,
  `ExecStart=<venv>/bin/python -m john_whisk.web`, `Restart=always`, enabled.
  Runs alongside `john-whisk.service`. Reachable at `http://192.168.88.12:8080`.
- Flask added to the venv (done).

## Data flow

Phone -> HTTP -> Flask route -> existing store module -> SQLite (same file the
voice app uses). Voice edits and web edits are immediately visible to each other
(each request opens its own SQLite connection; the modules already do this).

## Error handling

- Bad/missing JSON field -> 400 with a short message.
- Unknown recipe title -> 404.
- Store exceptions -> 500 with a generic message (logged).
- The web service failing never affects the voice service (separate process).

## Security / scope

- Bound to the LAN; intended for the home network only. No auth in v1 (documented
  as a limitation — add a token/PIN later if exposed).
- Read + edit of the kitchen stores only; does NOT touch the live in-memory
  cooking session (that stays voice-side).

## Testing (TDD)

- `create_app().test_client()`, DB paths isolated (conftest + monkeypatch):
  - `GET /` returns 200 HTML.
  - grocery: GET empty; POST add -> appears; remove -> gone; clear.
  - pantry: POST add -> GET shows it; remove.
  - recipes: seed a recipe -> `GET /api/recipes?q=...` finds it; view returns
    steps; unknown title -> 404.
  - settings: GET aggregates; POST restriction/equipment/flavor add + remove.
  - malformed POST -> 400.
- On-device: start the web service, curl the API, and load the page in a phone
  browser on the LAN; add a grocery item on the phone and confirm "what's on my
  grocery list" (voice) reflects it.

## Out of scope (future)

- Auth / exposure beyond the LAN; live cooking control from the phone; websockets/
  live refresh; a build-step SPA framework; theming.
