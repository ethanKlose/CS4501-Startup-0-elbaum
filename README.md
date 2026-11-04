# PlateJoy (alpha)

LLM-driven weekly meal planning for UVA students. Every LLM-generated plan passes through validators
(budget, restrictions, schedule, goal) and failures are fed back to the LLM to retry.

**Stack:** FastAPI · SQLAlchemy + SQLite · Jinja2 templates · Anthropic API (offline fake LLM when no key is set).

## Quick start
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
| `ANTHROPIC_MODEL` | default `claude-sonnet-5-5` |

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
   Sunday before the week.
3. **Validators** (`services/validators.py`):
   * **HARD** (plan is thrown away): format, one meal per slot, ingredient costs, budget, restrictions and
     free-text exclusions, pinned meals, rated-down meals.
   * **SOFT** (shown as a "Heads up" warning): cooking time per cook day, calorie target (weekly +/-10%, daily +/-30%),
     protein. Strict on attempts 1-2 (errors go back to the LLM), tolerated on the final attempt.
4. If hard checks never pass, `explain.find_conflicts` says which constraints conflict (budget, diet, pins).

Survey prep options (style, preferred cook days, session length) feed the scheduler.

## Features (GitHub issues #2-#27, #29-#32)
Survey (budget, busy days/minutes, restrictions, goal, free text, pantry, edit later) - plan generation + verification -
weekly calendar with a cooking plan (batch cooking) and meal detail - skip day / pin / regenerate / swap - consolidated grocery list
(pantry-aware, grouped, check-offs) - cooked/skipped, ratings, weekly check-in, leftovers to pantry.
Not in alpha: snack slot, Instacart (#28), migrations (Alembic), CSRF tokens, rate limiting.

## Deploy
`docker compose up --build` (SQLite lives in the `platejoy-data` volume). Any container host with a persistent
volume works (Fly.io, Render). Move to Postgres by changing `DATABASE_URL` once data outgrows SQLite.

## Layout
`app/routers` HTTP routes · `app/services` planner, validators, LLM clients · `app/templates` UI · `tests/` pytest · `scripts/seed.py`.
Alpha note: tables are created with `create_all` (no migrations yet) — `make reset` wipes the local DB after schema changes (**run it after pulling this version: new columns**).
