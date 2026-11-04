# PlateJoy (alpha)

LLM-driven weekly meal planning for UVA students. Every LLM-generated plan passes through validators
(budget, restrictions, schedule, goal) and failures are fed back to the LLM to retry.

**Stack:** FastAPI · SQLAlchemy + SQLite · Jinja2 templates · Anthropic API (offline fake LLM when no key is set).

## Quick start
Requires Python 3.11 or newer.

```bash
make setup     # venv, deps, copies .env.example -> .env
make run       # creates DB, seeds demo user, serves http://127.0.0.1:8000
make test      # pytest
```
Demo login: `demo@platejoy.dev` / `demo-password` (or sign up).

## Configuration (`.env`)
| Var | Purpose |
|---|---|
| `SECRET_KEY` | session signing; set a long random value in prod |
| `DATABASE_URL` | default `sqlite:///./platejoy.db` |
| `ANTHROPIC_API_KEY` | **put your key here.** Blank = deterministic offline fake LLM |
| `ANTHROPIC_MODEL` | default `claude-sonnet-5-5`; use a model available to your API account |
| `TIMEZONE` | calendar date calculations; default `America/New_York` |

## Where to put your Anthropic API key
1. `make setup` (creates `.env` from `.env.example`), then edit **`.env`** (git-ignored, never commit it).
2. Set `ANTHROPIC_API_KEY=sk-ant-...` and restart `make run`.
3. With no key the app uses `FakeLLM`: a deterministic, offline planner over a built-in recipe catalog. It is still
   subject to every validator, so the whole app (and all tests) work without a key.

## How generation works
1. **The LLM picks WHAT to eat** (`llm.generate_plan`): diet, budget, calories, protein, variety, shared ingredients.
2. **A deterministic scheduler picks WHEN to cook** (`services/schedule.py`). A busy Wednesday does not mean fewer
   meals: its dinner is cooked on Sunday/Tuesday in a batch and reheated. Reheating is free. Storage is safety-checked
   from the ingredients (fish 2 days, eggs 3, meat 4, other 5, fresh foods 1, else freezer). Cook day `-1` is the
   Sunday before the week. Cooking events finish before the earliest meal in each batch; the time grid expands for early prep.
3. **Validators** (`services/validators.py`):
   * **HARD** (plan is thrown away): format, one meal per slot, ingredient costs, budget, restrictions and
     free-text exclusions, the full pinned recipe, rated-down meals, and cooking deadlines.
   * **SOFT** (shown as a "Heads up" warning): cooking time per cook day, calorie target (weekly +/-10%, daily +/-30%),
     protein. Strict on attempts 1-2 (errors go back to the LLM), tolerated on the final attempt.
4. If hard checks never pass, `explain.find_conflicts` says which constraints conflict (budget, diet, pins).

Survey prep options (style, preferred cook days, session length) feed the scheduler.

New plans start next Monday, with a saved week-start date. Sunday prep is disabled when that Sunday is already today or in the past. Regenerate replaces the displayed future week; Plan next week advances to a new week and clears one-week eating-out skips. Old plans keep their own dates and cooking/rating history. A closed or completed meal cannot be swapped.

Grocery check-offs record the quantity actually purchased. At check-in, only those purchases count unless the user explicitly confirms buying the whole list. Settlement applies `current pantry + confirmed purchases - cooked ingredients` once. It never assumes that uncooked pantry stock was bought again. Unknown-quantity pantry entries remain unknown, and different units stay separate. Check-in closes cooking/status and shopping edits for that plan; feedback and ratings can still be edited. Replacing a plan also settles it, and a failed generation rolls the settlement back.

The ledger and explicit week date live in the existing plan settings JSON; these fixes add no database columns. Desktop users can switch between Calendar and Agenda. The header identifies offline demo mode when no API key is configured.

## Features (GitHub issues #2-#27, #29-#32)
Survey (budget, busy days/minutes, restrictions, goal, free text, pantry, edit later) - plan generation + verification -
weekly calendar with a cooking plan (batch cooking) and meal detail - skip day / pin / regenerate / swap - consolidated grocery list
(pantry-aware, grouped, check-offs) - cooked/skipped, ratings, weekly check-in, leftovers to pantry.
Not in alpha: snack slot, Instacart (#28), migrations (Alembic), CSRF tokens, rate limiting.

## Deploy
`docker compose up --build` (SQLite lives in the `platejoy-data` volume). Any container host with a persistent
volume works (Fly.io, Render). Compose explicitly sets the container URL to `sqlite:////data/platejoy.db`, overriding a relative host URL in `.env`.

Check persistence before using it with real data: create a test account, run `docker compose down` and `docker compose up -d`, then log back in. Do not use `down -v`, which intentionally deletes the volume. Docker execution and live Anthropic generation were not available during the local fix verification.

## Layout
`app/routers` HTTP routes · `app/services` planner, validators, LLM clients · `app/templates` UI · `tests/` pytest · `scripts/seed.py`.
Alpha note: tables are created with `create_all` (no migrations yet). These fixes do not require a reset for an existing database compatible with the base alpha commit. `make reset` deletes the default local database; use it only when you intend to discard local data.

## Browser smoke test
Requires Node.js 20 or newer, in addition to the Python setup above.

```bash
npm ci
npx playwright install chromium
make test-e2e
```

The test starts its own local app with a disposable database and no API key. It covers onboarding, generation, recipe actions, exact pin preservation with the demo planner, blocked completed-meal swaps, day controls, failed grocery-save rollback, pantry editing, check-in, week advancement, theme, phone/tablet layouts, and login/logout. CI runs both pytest and this browser check. A failure screenshot is written to the ignored `test-results/` directory.

See `START_HERE.md` for the downloadable repository instructions and `FIXES.md` for the commit map and validation results.
