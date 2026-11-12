# Beta integration verification

Base: `KS_Work` commit `a76de37`, tree `0e324e15bc13f5da5a5f058e47fca2c5ecc53601`.
The local patch baseline was byte-for-byte tree matched to that GitHub merge.

- **653 Python tests passed**, zero failed; 964 existing/new deprecation warnings;
  184.84 seconds on Linux / Python 3.12.14, with coverage enabled.
- Count: **581 existing + 24 new free OpenAI cost-guard checks + 48 new Beta tests**.
- New Beta tests: **20 Google HTTP/database workflow cases, 25 calendar/Instacart
  boundary cases, 3 Instacart preview/cache workflow cases**.
- **95.98% Python application statement-line coverage**: 2,933 of 3,056 executable
  statement lines under `app/`. This does not measure HTML/CSS/JavaScript, real
  account consent, provider availability or the quality of generated meal plans.
- Feature-focused collection has 56 cases, including eight retained Instacart
  integration cases. The default suite includes all of them.
- **Five opt-in live tests collected and skipped without their enable flags**:
  three OpenAI, one Google, one Instacart. **No real provider requests were made
  in this development environment.** No API key or account was available here.
- Ten new manual acceptance procedures are written, **not executed by a human**.
- Browser tests were not rerun for this patch because browser startup is blocked
  in this environment; neither Google consent nor the Instacart shopping page is
  claimed to have passed in a browser.

Regular integration tests exercise real routes, sessions, CSRF, migrations,
persistence and adapter code with controlled HTTP provider responses. Paid/live
tests use the real network, require explicit flags and are separate evidence.

Commands and provider configuration are in `BETA_INTEGRATIONS.md` and
`LIVE_OPENAI_TESTS.md`. Raw results and the count/coverage summary are in
`docs/evidence/beta/`. Historical reports elsewhere describe their earlier commits
and should not be mistaken for the current test run.
