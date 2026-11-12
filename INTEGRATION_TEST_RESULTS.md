# Integration test results

## Windows compatibility correction

The initial fixture incorrectly blocked the loopback TCP connection that CPython
uses to construct `socket.socketpair()` on Windows. This prevented the async
TestClient from starting; it was a test-harness failure, not 70 independent
product failures. A new regression reproduced the same failure before the fix.

The guard now allows loopback connections only during standard-library socketpair
construction in that thread. Ordinary application connections, including direct
loopback connections, remain blocked. No application code or dependency changes
were needed.

| Correction validation | Recorded local result |
| --- | --- |
| Windows socketpair regression before correction | 1 failed, reproducing the reported startup error |
| Same regression after correction | 1 passed |
| Migration test plus integration directory | **72 passed**, 0 failed, 0 errors; 20.08 seconds |
| Current explicitly marked integration cases | **71**: original 70 plus the socketpair regression |
| Complete Python suite with TCP socketpairs forced globally | **579 passed**, 0 failed, 0 errors; 178.86 seconds |
| Current Python application line coverage | **97.37%**, 2,559 / 2,628 statements |

The full correction run reported 903 deprecation warnings; the targeted run
reported 253 warnings. Raw red/green logs, JUnit and coverage are preserved in
`docs/evidence/integration/windows-fix/`. The full run replaced `socket.socketpair`
with CPython's `_fallback_socketpair` before pytest started, exercising the
Windows-style TCP construction throughout the run on Linux/Python 3.12. This is
not a claim that native Windows/Python 3.13 was locally available. Hosted CI now
covers Ubuntu and Windows with both Python 3.11 and 3.13.

## Initial integration delivery (historical)

Verified source baseline: `07e67867a159a17bfe876ee5ae4896bd10ec4e81` on `KS_Work`,
plus the integration-suite, CI and documentation changes in this delivery.

| Measure | Recorded local result |
| --- | --- |
| New explicitly marked integration cases | **70 passed**, 0 failed, 0 skipped; 19.97 seconds |
| Complete Python suite | **578 passed**, 0 failed, 0 skipped; 175.59 seconds |
| Existing Python cases retained | **508**; no existing cases removed or counted as new |
| Python application line coverage | **97.37%**, 2,559 / 2,628 executable statements |
| Uncovered executable statements | 69 |
| Coverage gate | Passed: at least 90% |
| Anthropic minimum-version check | All 9 LLM integration cases passed with SDK **0.40.0** |
| Anthropic fresh-install check | All 9 LLM integration cases passed with SDK **2.8.0**, also included in the complete suite |
| Browser smoke and audit reruns | **Blocked before browser workflows started** by Chromium's required socket being denied in this runtime |
| Hosted Ubuntu / Windows integration CI | Configured; not claimed as executed during local verification |

The new suite has 47 application workflow/security cases and 23 provider-boundary
cases. All 70 are automated, including the SMTP/outbox cases. The 24 previously
documented manual procedures were not executed or relabeled as automated cases.
Some of the existing 508 tests already exercise integrated behavior; they are
preserved without pretending these additions are the first integration coverage.

The complete run reported 900 warnings, primarily existing deprecated UTC datetime
usage and a dependency deprecation. The standalone integration run reported 250
warnings. These runs passed, but do not establish warning-free execution.

## Evidence

`docs/evidence/integration/` contains the complete and integration-only JUnit XML,
the collected case names, the full-suite and integration summaries, the coverage
JSON and text report, the SDK compatibility result and the browser startup error.
Generated temporary paths in JUnit refer to disposable local test environments.

The real application, middleware, migrations and SQLite transactions were used.
No production application behavior or dependency requirements changed. HTTP/SMTP
provider transports were controlled and no live key, purchase, paid model call or
external email was used. Calendar checks cover ICS export, not Google OAuth sync.

These initial runs were on Linux with Python 3.12.14. The initial CI configuration
targeted Python 3.11 on Ubuntu and Windows; the compatibility correction above
adds Python 3.13. Configured CI is separate from a completed native Windows run.

This work adds regression/integration coverage to existing code; it does not
retroactively prove that original implementation followed a red/green TDD cycle.
