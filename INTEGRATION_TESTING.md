# Application integration testing

The integration suite adds **71 automated cases** under `tests/integration/`
(the original 70 plus one Windows event-loop regression).
It supplements the 508 existing Python cases and the two existing Playwright
workflows. Existing tests are not relabeled or counted again as new cases.

## Run locally (Windows, macOS or Linux)

Activate your project virtual environment first, then run from the repository root:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests/integration -m integration -q --strict-markers --junitxml=test-results/integration.xml
```

To run the complete Python suite and measure application line coverage:

```bash
python -m coverage run --source=app -m pytest -q --strict-markers --junitxml=test-results/python-suite.xml
python -m coverage report --fail-under=90
python -m coverage json -o test-results/python-coverage.json
```

`make test-integration` is an optional shortcut on systems with Make. On Windows
you can use `.venv/Scripts/python.exe` instead of `python` in these commands.
No Anthropic, Instacart or SMTP credentials are needed. Tests use a temporary
database and outbox, not your `.env`, existing database or actual email account.

## What makes these integration tests

Requests go through the real FastAPI routes, signed sessions, CSRF middleware,
form parsing, SQLAlchemy sessions, application services and rendered templates.
Application startup runs the real Alembic migration against a separate temporary
SQLite file for each case. The suite does not override `get_db` or replace the
planner, validators, scheduler, inventory or authentication services with mocks.
Assertions read committed results through separate database sessions.

The clock, random seed and configuration are controlled for reproducibility.
Application network connections are blocked. Only the standard library's internal
loopback TCP socketpair construction is allowed, in the constructing thread, so
Windows asyncio can create its wake-up pipe. Third-party HTTP or SMTP responses are replaced
at the I/O boundary only. Browser behavior is covered separately by Playwright;
FastAPI's TestClient does not execute frontend JavaScript.

## Coverage matrix

Story numbers below are the GitHub issue numbers used by the acceptance documents.

| Integration area | Connected components and observable outcomes | Cases | Stories |
| --- | --- | ---: | --- |
| Planning workflows | Survey, diet/preference parsing, kitchen/schedule settings, catalog selection, validators, price/pantry snapshots, persisted meals, calendar and recipe pages, pins/swaps/skips, today-mode and visible nutrition warnings | 11 | #2-#26 |
| Identity and persistence | Registration/login/logout, normalized email uniqueness, password hashing, CSRF rotation, signed cookies, real startup migrations, application restart, per-account quotas and 12 cross-account resource attacks | 26 | Account/security foundation for all stories |
| Inventory and feedback | Grocery purchases, cooked/rated meals, inventory balance, repeated/concurrent check-ins, undo with manual corrections, next-week feedback, archived history, consented exports and calendar-file structure | 10 | #17-#18, #24-#26, #28-#32 |
| LLM boundary | Actual Anthropic SDK request/response processing, catalog hydration, untrusted-field replacement, validation feedback, bounded retries and rollback preserving the previous plan and purchase ledger | 9 | #6, #10-#15, #22-#23 |
| Shopping provider | Actual Instacart adapter, unchecked-item payload, cached link reuse/invalidation, missing credentials, empty lists, timeout/status/JSON failures and untrusted redirects | 8 | #24-#28 |
| Password recovery | Real development outbox or controlled SMTP transport, verified TLS setup, token hashing, expiry/single use, password change, session revocation and generic failure responses | 6 | Account/security foundation for all stories |
| Windows event loop | Force CPython's Windows-style TCP socketpair, start the real application, generate a plan, exchange wake-up bytes, and confirm application network calls are still rejected | 1 | Test-fixture compatibility |
| **Total new automated cases** | **Each parameter combination is one collected pytest case** | **71** | **All six Alpha feature groups** |

The mapping covers workflows associated with all 31 story records. It is not a
claim that every acceptance criterion has been proven. Human onboarding duration,
user preference, real shopping prices and product usability remain outside this
automated suite. The 24 existing manual procedures remain manual and unexecuted.

## Provider boundaries

* **Anthropic:** The real installed SDK and application adapter build requests and
  consume controlled provider responses. Both older HTTPX-backed and newer
  HTTPX2-backed SDK transports are supported. No model is queried, so these tests
  do not measure live response quality, token billing or production availability.
* **Instacart:** The real adapter constructs a shopping-list link request and
  handles controlled responses. Tests never create an external list or order.
* **SMTP:** The real mail adapter builds the message, requests certificate-verified
  TLS and performs the login/send sequence against a controlled SMTP object.
  Another case uses the real local JSON outbox and follows its reset URL through
  the real password-reset endpoint. Actual email delivery is not tested.
* **Calendar:** Tests fetch and structurally parse actual ICS responses, checking
  CRLF boundaries, line folding, complete events, dates, stable unique IDs and
  privacy. This does not establish Google Calendar OAuth or synchronization.

## CI and evidence

GitHub Actions has dedicated integration jobs on Ubuntu and Windows with Python
3.11 and 3.13, with JUnit
results uploaded even when a test fails. The full Python job also includes these
71 cases and retains its 90% line-coverage gate. The browser jobs remain separate.
Adding a CI configuration is not evidence that the hosted Windows job has run.

See `docs/evidence/integration/` for the recorded local run, collected-case
inventory, JUnit results, coverage and the environment limitation affecting the
browser rerun. Historical evidence elsewhere in `docs/evidence/` is preserved.

These are regression/integration additions for existing functionality. They do
not establish that the original production code was developed test-first.
