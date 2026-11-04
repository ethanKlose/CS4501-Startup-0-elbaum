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

## Deploy
`docker compose up --build` (SQLite lives in the `platejoy-data` volume). Any container host with a persistent
volume works (Fly.io, Render). Move to Postgres by changing `DATABASE_URL` once data outgrows SQLite.

## Layout
`app/routers` HTTP routes · `app/services` planner, validators, LLM clients · `app/templates` UI · `tests/` pytest · `scripts/seed.py`.
Alpha note: tables are created with `create_all` (no migrations yet) — `make reset` wipes the local DB after schema changes.
