# PlateJoy (alpha)

Current work branch: `KS_Work`. See [HOW_TO_RUN_LOCALLY.md](HOW_TO_RUN_LOCALLY.md) for Windows commands, and [KS_WORK_IMPROVEMENTS.md](KS_WORK_IMPROVEMENTS.md) for the new feature and validation notes.

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

Plans can start next Monday or cover the rest of the current week, with a saved week-start date. Sunday prep is disabled when that Sunday is already today or in the past. Regenerate replaces the displayed future week; Plan next week advances to a new week and clears one-week eating-out skips. Old plans keep their own dates and cooking/rating history. A closed or completed meal cannot be swapped.

Grocery check-offs record the quantity actually purchased. Check-offs capture whole package quantities, including surplus. At check-in, only those purchases count unless the user explicitly confirms buying the whole list. Settlement applies `current pantry + confirmed purchases - cooked ingredients` once. It never assumes that uncooked pantry stock was bought again. Unknown-quantity pantry entries remain unknown, and different units stay separate. Check-in closes cooking/status and shopping edits for that plan; feedback and ratings can still be edited. Replacing a plan also settles it, and a failed generation rolls the settlement back.

The inventory ledger and week date live in plan settings JSON. Alembic adopts existing alpha tables and adds separate preference/security tables without deleting accounts or plans. Desktop users can switch between Calendar and Agenda. The header identifies offline demo mode when no API key is configured.

## Features (GitHub issues #2-#32)
Survey (budget, busy days/minutes, restrictions, goal, free text, pantry, edit later) - plan generation + verification -
weekly calendar with a cooking plan (batch cooking) and meal detail - skip day / pin / regenerate / swap - consolidated grocery list
(pantry-aware, grouped, check-offs) - cooked/skipped, ratings, weekly check-in, leftovers to pantry.
Not implemented: snack slots, live store-price feeds, Instacart checkout or automatic Google Calendar synchronization. Calendar export, Alembic migrations, CSRF protection and rate limits are implemented.

## Deploy
`docker compose up --build` (SQLite lives in the `platejoy-data` volume). Any container host with a persistent
volume works (Fly.io, Render). Compose explicitly sets the container URL to `sqlite:////data/platejoy.db`, overriding a relative host URL in `.env`.

Check persistence before using it with real data: create a test account, run `docker compose down` and `docker compose up -d`, then log back in. Do not use `down -v`, which intentionally deletes the volume. Docker execution and live Anthropic generation were not available during the local fix verification.

## Layout
`app/routers` HTTP routes · `app/services` planner, validators, LLM clients · `app/templates` UI · `tests/` pytest · `scripts/seed.py`.
Database migrations run on startup and from `python -m alembic upgrade head`. Existing compatible alpha tables are adopted non-destructively. `make reset` deletes the default local database; it is not an upgrade command.

## Integration tests
For application integration tests, run `python -m pytest tests/integration -m integration -q`
from your active virtual environment. The 70 integration cases exercise actual routes,
middleware, database migrations and service workflows with controlled external I/O.
See [INTEGRATION_TESTING.md](INTEGRATION_TESTING.md) for the coverage matrix,
Windows commands, CI configuration and the limits of provider testing.

## Browser smoke test
Requires Node.js 20 or newer, in addition to the Python setup above.

```bash
npm ci
npx playwright install chromium
make test-e2e
```

The test starts its own local app with a disposable database and no API key. It covers onboarding, generation, recipe actions, exact pin preservation with the demo planner, blocked completed-meal swaps, day controls, failed grocery-save rollback, pantry editing, check-in, week advancement, theme, phone/tablet layouts, and login/logout. CI runs both pytest and this browser check. A failure screenshot is written to the ignored `test-results/` directory.

See `START_HERE.md` for the downloadable repository instructions and `FIXES.md` for the commit map and validation results.


## New student workflows

- `/survey`: equipment, skill, dining-hall meals, cooking windows and meal times.
- `/prices`: whole-package sizes, local receipt prices, provenance and observation dates. Built-ins remain demo estimates.
- `/plans`: private plan history. Each plan can export `.ics`; import it into a calendar app. This is export, not autonomous two-way synchronization.
- `/checkin`: settlement and an undo action for the latest plan. Undo rejects reversals that would require removing stock already used elsewhere.
- `/forgot-password`: expiring single-use recovery links. Configure SMTP for delivery; local development uses a non-public `.local-mail` outbox.
- `/feedback`: actual spending, planning time, baseline and usability results with optional numeric-export consent. See `USABILITY_STUDY.md`.

## Live evaluation

```bash
# In the configured Python virtual environment:
python -m scripts.evaluate_planner --output evals/offline-baseline.json
python -m scripts.evaluate_planner --live --repeats 2 --output evals/live-results.json
```

The live command requires your own API key and may incur charges. An absent key produces an honest unavailable report and exit code 2. Costs remain unknown unless you supply evaluation-only per-million-token rates. No live results or human-study results are fabricated. See `DATA_SOURCES.md` for USDA nutrient provenance and measurement assumptions.

## Production configuration

Set `APP_ENV=production`, an unpredictable `SECRET_KEY` of at least 32 characters, and an HTTPS `PUBLIC_BASE_URL`. Cookies become secure and default secrets are rejected. Configure SMTP credentials for real password recovery. `scripts.seed` does not create a demo account in production. Keep secrets in `.env`/the host secret store, not Git. Container access logs are disabled to avoid recording recovery tokens in URL queries. SQLite serializes writes; migrate to PostgreSQL before a larger multi-user rollout and load-test the deployment.

## Story completion and manual acceptance tests

See [STORY_COMPLETION.md](STORY_COMPLETION.md) for the six commit groups, automated results, and remaining external/manual checks. The 31 stories have individual acceptance evidence in [docs/acceptance](docs/acceptance/). [MANUAL_TESTS.md](MANUAL_TESTS.md) links 24 explicitly manual procedures and editable execution logs in four requested categories. Manual cases are not counted as automated passes or human study results.

### Optional Instacart handoff (story #28)

The grocery page offers **Send to Instacart**. It shares only unchecked, pantry-adjusted ingredients and creates a shopping-list link, not an order or automatic purchase. Configure `INSTACART_API_KEY` and `INSTACART_ENV=development` in your local `.env` for a development key; production keys use `INSTACART_ENV=production`. Restart the app after configuration. Never commit the key.

Without a key, a clear message keeps your list available. Provider timeouts, HTTP errors, invalid JSON and untrusted links fail safely. Identical lists reuse their link for up to six days; changed quantities invalidate the cached link. The API requests seven-day links. Unknown ingredient units are included as display text without a measurement; review and adjust those quantities in Instacart. Its actual prices, product matches, labels and delivery availability require review there.

Official API contract: https://docs.instacart.com/developer_platform_api/api/products/create_shopping_list_page . Live acceptance requires an Instacart development account/key and is not claimed by mocked tests.
