# KS_Work improvements

Based on the fetched `origin/KS_Work` commit `b0ee1e401f61405408aff9440f06ba7a6fa38544`. New work stays on `KS_Work`. Nothing was pushed to GitHub.

## Completed scope

| Gap | Implementation |
| --- | --- |
| Trusted nutrition | USDA SR Legacy per-ingredient nutrient snapshot, source IDs and gram assumptions; live AI selects approved recipes and cannot override nutrients, quantities or steps. |
| Shopping realism | Whole-package checkout budgets, separate portion totals, local package-price overrides with source/date, and surplus carried into pantry inventory. |
| Student constraints | Kitchen equipment, beginner recipes, freezer availability, fridge-free daily cooking and dining-hall/external meal slots. |
| Real scheduling | Explicit cooking windows, editable meal times, no past cooking on a plan starting today, and private calendar export. |
| Flexible use | Current/rest-of-week planning, private plan history, archived recipes, and check-in undo that reverses inventory deltas. |
| Concurrent updates | Database-backed user write locks and a parallel-worker exactly-once settlement test; stale plan submissions are rejected. |
| Live AI reliability | Explicit SDK timeout, bounded application retries/output size, validated preference extraction, stored attempt/usage metrics and an evaluation CLI. |
| Deployment security | CSRF for forms and AJAX, persistent rate counters, production secret/HTTPS-cookie enforcement, verified SMTP TLS, recovery/session revocation and safer access logs. |
| Data upgrades | Alembic baseline safely adopts compatible alpha tables and creates preference/security tables; existing account/plan data survive. |
| User evidence | Spending/usability feedback form, optional numeric-export consent, privacy-preserving export and a student-study procedure. |
| Windows | Explicit tzdata dependency and retained platform-specific running instructions. |

## Separate commits

| Commit | Change |
| --- | --- |
| `dfb7a64` | Include timezone data for Windows installations |
| `56ad436` | Adopt existing databases with non-destructive Alembic migrations |
| `5609028` | Protect every form and AJAX mutation with session-bound CSRF tokens |
| `aea6c2d` | Serialize inventory and plan writes across workers and tabs |
| `1bfc367` | Rate-limit authentication and generation and enforce production settings |
| `f2a32ab` | Add expiring single-use password recovery and session revocation |
| `736896f` | Add private plan history and reversible check-in settlement |
| `0613895` | Plan around kitchen equipment, skill level, freezer access and campus meals |
| `b79d79d` | Respect cooking windows and adjustable meal times in the calendar |
| `8fe4fa0` | Support planning from today without assigning past meals or prep |
| `6c8576f` | Derive nutrition from USDA ingredients and constrain AI to approved recipes |
| `cb2c85f` | Budget whole-package shopping and support sourced local price overrides |
| `c50cade` | Bound live AI calls and add token, retry, latency and cost evaluation |
| `2e19f9c` | Export private meal and cooking calendars for external calendar apps |
| `33b735f` | Collect consented student feedback and export numeric study results |
| `aaa7fa5` | Carry whole-package surplus into pantry settlement |
| `1e16364` | Include migration files in containers and repair recovery page layout |
| `6aa579d` | Expose nutrient provenance and finish constraint and evaluation integration |
| `4e61ee1` | Protect study pseudonyms and avoid recovery tokens in container access logs |
| `5608ab4` | Exercise the new student workflows in the browser smoke test |
| `0615073` | Optimize demo plans for checkout budgets and validate AI preference extraction |
| `62b28ff` | Keep legacy plans readable when package-price mappings are missing |
| `9b26ae6` | Verify mail-server TLS and keep production CSRF cookies secure |
| `85d89c0` | Check HTTP rate limits, revoked sessions and microwave-only plans |

The following documentation commit records these results and packages the update instructions.

## Verification

**Final full Python suite: 422 passed, 563 deprecation warnings, in 63.73 seconds on Python 3.12.**
- Expanded browser smoke test passed account creation, preferences, automatic generation, quick view, recipe actions, pin regeneration, protected completed meals, day controls, grocery persistence and failed-save rollback, pantry editing, theme, tablet/phone layouts, history, check-in undo, local-price provenance, kitchen/windows forms, CSRF rejection, feedback, calendar export, next-week advancement and login/logout. No browser JavaScript exceptions were observed.
- Offline evaluation completed six scenarios with a success rate of 1.0. The report is explicitly labelled `fake`; it is not evidence of real-model quality.
- The live evaluation command was invoked and returned status `unavailable` with no results because ANTHROPIC_API_KEY is absent. Its exit code is 2. See `evals/live-status.json`.
- Migrations were run twice against a legacy-shaped database and preserved an existing account. A file-backed two-worker test verified inventory settlement happens once.
- Password recovery tests cover single use, old-password rejection and revocation of existing sessions. SMTP is stubbed in tests; no real email was sent.
- Python compilation, JavaScript syntax, whitespace checks and YAML parsing were checked.

## External checks that remain unverified

- Actual Anthropic quality, rate-limit behavior and billed cost require your API key and a model available to that account. Run `python -m scripts.evaluate_planner --live --repeats 2` after configuring `.env`.
- Real SMTP delivery needs configured mail credentials. Local development uses a non-public outbox instead.
- Docker container recreation and a deployed multi-user load test were not executed. Migration files are now included in the image. SQLite serializes writes, so use and load-test PostgreSQL before a larger rollout.
- No students were contacted and no human usability results were invented. `USABILITY_STUDY.md` explains how to collect them with consent.
- Built-in prices remain demo estimates. They are not live supermarket quotes. Local receipt prices improve the estimate but are user-entered and not independently authenticated.
- USDA measurements use the documented raw/cooked choices and portion assumptions; they are sourced estimates rather than individual-product nutrition or allergen guarantees.
- Calendar integration is `.ics` export, not autonomous two-way Google Calendar synchronization.

## Importing the commits

Use `APPLY_UPDATES.md` to fetch the included bundle into your existing checkout. It preserves your local environment and database files. Install the updated requirements before starting the app; Alembic and tzdata are required. The existing `HOW_TO_RUN_LOCALLY.md` has Windows commands.
