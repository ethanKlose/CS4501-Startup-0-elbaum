# Kroger integration verification

- **724 Python tests passed**, zero failed, 1,063 deprecation warnings, in 217.68
  seconds with application coverage enabled on Linux / Python 3.12.14.
- This includes **63 new Kroger tests**: 35 HTTP/database workflow cases and 28
  credential/identifier/quantity/size/format boundary cases.
- Count: 653 Beta tests + 8 optional calendar-color tests + 63 Kroger tests = 724.
  A checkout without the optional calendar-color update has 716 default cases.
- **95.39% Python application statement-line coverage**: 3,332 of 3,493 executable
  statement lines under `app/`. This does not measure browser rendering, live
  provider availability, registration eligibility or actual checkout behavior.
- The incremental patch was applied and compared against clean CRLF checkouts
  both with and without the calendar-color update. On the latter, **84 focused
  Kroger/Google/ICS regression cases passed** in 12.89 seconds.
- The new test suite exercises real application routes, sessions, CSRF, migrated
  databases, token encryption/persistence and product/cart adapters. Kroger HTTP
  responses are controlled. **No real Kroger API or OpenAI requests were made.**
- Six live cases collected and skipped without opt-in flags: three OpenAI, one
  Google, one Instacart, one new read-only Kroger smoke test. The Kroger live test
  does not add products to a cart, purchase anything or consume OpenAI tokens.
- Ten new manual acceptance procedures are written, **not executed by a human**.
- Browser UI tests were not rerun for this update. Real developer registration,
  OAuth consent, retailer product availability and the cart write remain account
  owner acceptance checks. No live or human test results are fabricated.

Successful test output and structured counts/coverage are in
`docs/evidence/kroger/`. Setup, limits, manual review and failure recovery are in
`KROGER_SETUP.md`; manual procedures are in `docs/manual/KROGER_MANUAL_TESTS.md`.

The new workflow does not place orders, automatically check off purchases or
replace Google Calendar tokens. Repeated and concurrent submissions are tested
against a durable pending marker; uncertain cart writes require the user to check
Kroger before another transfer is allowed.
