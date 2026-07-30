# Meal-Planning Calendar + Upcoming Awareness — Design

Status: approved 2026-07-29. A calendar for John Whisk: schedule dishes onto
dates, add personal events, and ask what's coming up (planned meals + events +
holidays + season) days/weeks/months ahead. Fully offline now; a Google Calendar
sync is a designed-for future phase. Built in phases.

## Decisions (from brainstorming)

- **Meal plan:** dinner-focused, multiple dishes per day, no rigid meal slots.
- **Personal events:** entered manually by voice now ("I have dinner plans
  Thursday"); real-calendar sync via **Google Calendar OAuth is DEFERRED** to a
  later phase (read-only-cache design, so the voice assistant never needs
  internet to work).
- **Awareness:** "what's coming up" combines planned meals, personal events,
  upcoming holidays (curated), and the current season (reuse `seasonal.py`).
- **Auto features:** planning a meal can add its missing ingredients to the
  grocery list; a planned meal you ate can roll into the nutrition daily log.
- **Scope notes:** holidays are a curated US/common list; the date parser
  targets common phrasings, not arbitrary natural language.

## Components

### `john_whisk/mealplan.py` — the module
Store + logic, following the codebase idioms (`contextlib.closing`, `init_db`,
small local helpers). Tables live in `config.DB_PATH`.

Tables:
- `meal_plan(id, plan_date TEXT, dish TEXT, added_at TEXT)` — many dishes/day.
- `events(id, event_date TEXT, description TEXT, added_at TEXT)` — personal events.

Dates are stored as ISO `YYYY-MM-DD` strings.

### Shared date parser — `parse_date(text, now=None)`
Returns a `datetime.date` or None. Supported forms:
- `today` / `tonight` -> today; `tomorrow` -> +1 day.
- Weekday names ("friday") -> soonest occurrence (today if it matches);
  "next friday" -> that + 7 days.
- `in N days` -> +N.
- Explicit month + day ("july 4", "july 4th", "4th of july") -> that date this
  year, or next year if already past.
- Day-of-month ("the 12th") -> that day this month, or next month if past.
- Unparseable -> None. `now` is injected for deterministic tests.

### Curated data
- `HOLIDAYS` — a dict of (month, day) -> name for fixed-date US/common holidays
  (New Year's, Valentine's, July 4th, Halloween, Christmas, etc.) plus a small
  set computed where easy (Thanksgiving = 4th Thursday of November).
- Season comes from `seasonal.in_season(month)`.

### Functions
- `add_plan(date, dish)` / `plan_for(date)` / `remove_plan(id)` / `clear_date(date)`.
- `add_event(date, description)` / `events_for(date)`.
- `week(start=None, days=7)` -> ordered [{date, weekday, dishes:[...],
  events:[...], holiday, }] for the window (used by voice + dashboard).
- `holiday_on(date)` / `upcoming_holidays(now, days)`.
- `upcoming(now=None, days=7)` -> a structured look-ahead: planned meals,
  events, and holidays within the window, plus the current season.
- Spoken answers: `answer_plan(text, now)` ("what am I making Friday / this
  week / tonight"), `answer_upcoming(text, now)` ("what's coming up"),
  and set/add confirmations.

### Router intents (`router.py`)
Add, placed before `plan` (the grocery meal-planner) and `suggest` so calendar
phrasings win:
- `plan_set` — "plan X for/on <day>", "put X on the menu/calendar <day>",
  "add X to <day>'s plan", "schedule X <day>".
- `plan_query` — "what am I making <when>", "what's for dinner tonight",
  "what's on the menu", "my meal plan".
- `event_add` — "I have <event> on <day>", "I've got <event> <day>",
  "add an event".
- `calendar_query` — "what's coming up", "what's on my calendar <when>",
  "anything going on <when>", "what's this week/month".

Precedence care: `plan_set`/`plan_query` must beat the existing `plan` intent
(grocery "I would like to make X") and `cook`; `calendar_query` must not be
swallowed by `suggest`. Handlers live in `mealplan`.

### Main dispatch (`main.py`)
Route the four intents to `mealplan` handlers.

### Dashboard (`web.py`) — a new "Plan" tab
A week view (with a way to look further out): each day shows its planned dishes
(removable) and events, with holidays/season marked; an add field to plan a dish
or event on a chosen day. JSON API mirrors existing patterns:
`GET /api/plan?days=N` -> the window; `POST /api/plan` {date, dish};
`POST /api/plan/remove` {id}; `POST /api/event` {date, description};
`POST /api/event/remove` {id}.

## Phasing

1. **Calendar core (offline):** `parse_date`, `meal_plan` store, `add_plan`/
   `plan_for`/`week`, `plan_set` + `plan_query` intents + `answer_plan`, and the
   dashboard Plan tab (meals only).
2. **Events + upcoming (offline):** `events` store, `HOLIDAYS` + `holiday_on`/
   `upcoming_holidays`, `event_add` + `calendar_query` intents, `upcoming` +
   `answer_upcoming` (meals + events + holidays + season); events shown on the
   Plan tab.
3. **Auto features (offline):** planning a meal offers to add missing
   ingredients to grocery (reuse `grocery`/`recipes`); "I ate my planned <day>
   dinner" rolls into `nutrition` log.
4. **Deferred / future:** Google Calendar sync (read-only cache; OAuth).

Each phase ships and is tested before the next.

## Data flow

Voice/dashboard -> `mealplan` -> SQLite (`DB_PATH`, shared with voice + web).
`upcoming` reads meal_plan + events + HOLIDAYS + `seasonal`. Auto features call
into the existing `grocery` and `nutrition` modules.

## Error handling

- Unparseable date -> ask the user to rephrase ("Which day?").
- Empty dish/event -> prompt for it.
- Querying a day with nothing planned -> say so plainly.
- Bad id on remove (dashboard) -> 400.

## Testing (TDD)

Deterministic; `now` injected everywhere dates are involved.
- `parse_date`: today/tonight/tomorrow, each weekday, "next" weekday, "in N
  days", "july 4th", "the 12th", unparseable -> None.
- store: add/query/remove plans and events; multiple dishes per day; date
  isolation.
- `week`/`upcoming`: correct window, groups meals+events+holidays, season.
- `HOLIDAYS`/Thanksgiving computation.
- router: each intent classified; precedence vs `plan`/`cook`/`suggest`.
- main dispatch; dashboard endpoints (add/query/remove meals + events).
- LLM never on the hot path (planning/lookups are deterministic).

## Out of scope (now)

- Google/Apple calendar sync (Phase 4, future).
- Recurring events, reminders/notifications, times-of-day, meal slots
  (breakfast/lunch), multi-person plans.
