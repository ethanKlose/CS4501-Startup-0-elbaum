# Integration test results

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

These runs were on Linux with Python 3.12.14. CI targets Python 3.11 on Ubuntu
and Windows. That configuration is separate from a completed native Windows run.

This work adds regression/integration coverage to existing code; it does not
retroactively prove that original implementation followed a red/green TDD cycle.
