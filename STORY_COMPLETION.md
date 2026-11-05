# User-story completion package

Implementation/acceptance evidence is supplied for all **31 user stories (#2-#32)**. Existing working features were retained; only remaining gaps were changed. Six commits group five stories each in the first five groups and six in the last. No GitHub issues were closed or remote branches changed by this task. The aggregate automated cases/story average is 508 / 31 = 16.39; 24 manual procedures are counted separately.

## Changes by commit group

| Group | Stories | Commit / change |
| --- | --- | --- |
| 1 | #2-#6 (5 stories) | faf8099: exact integer survey inputs, explicit errors for unknown diet choices, red-meat/chicken-only parsing and readback evidence |
| 2 | #7-#11 (5 stories) | 6d702f8: pantry limits without silent truncation; bounded plan shape, nonblank names/steps, optional onboarding and saved edits |
| 3 | #12-#16 (5 stories) | e59aa61: deduct pantry stock from remaining ingredient costs; use actual required slots/kitchen rules in failure explanations; normalized sharing statistics |
| 4 | #17-#21 (5 stories) | 5b6becf: strict HH:MM cooking windows and eight-window cap; preserve closed history and remove inactive pin controls |
| 5 | #22-#26 (5 stories) | 11fc3fc: normalized grocery units and ingredient names, partial pantry deductions, duplicate/missing-slot and single-swap acceptance evidence |
| 6 | #27-#32 (6 stories) | Final package commit: optional Instacart handoff, cache/timeout/response validation, rating reset, check-in enum/length errors, CI and consolidated evidence |

Per-story traceability: [docs/acceptance](docs/acceptance/). Original story text: [snapshot](docs/USER_STORIES_SNAPSHOT.json). A shared regression file can validate several related criteria; tests per issue is an aggregate rather than a one-to-one mapping.

## Executed automated validation

- **508 passed, 0 failed**, with 651 existing/dependency deprecation warnings, in 142.67 seconds on Python 3.12.14. Baseline: 453 passing cases; this package adds **55 passing cases**.
- Python line coverage: **95.32%**, 2505/2628 executable lines under `app/`. HTML, JavaScript and manual execution are not included in that denominator. No coverage exclusions were applied.
- Full browser smoke and expanded audit-regression workflows passed in Chromium 153.0.8010.0 with Playwright 1.62.1. No page JavaScript exceptions were recorded. The audit exercises actual browser form serialization for Instacart unavailable handling and closed-history controls.
- Offline benchmark: 20 configurations x 3 fixed seeds = **60 runs**; **57 accepted**, **54 passing every encoded check without warnings**, 3 accepted with outside-meal nutrition warnings, 3 rejected $30-budget searches. These are engineering cases, not students. Raw results: [JSON](docs/evidence/story-planner-benchmark.json) / [CSV](docs/evidence/story-planner-benchmark.csv).
- Python compilation, JavaScript syntax and Git whitespace checks passed. CI now includes pushes to KS_Work, both browser workflows, a 90% Python application coverage gate and a coverage artifact. That CI configuration was inspected locally; a new hosted Actions run is not claimed.

Evidence: [Python summary](docs/evidence/python-test-summary.txt), [coverage](docs/evidence/python-coverage.txt), [browser smoke](docs/evidence/browser-smoke.txt), [browser audit](docs/evidence/browser-audit.txt).

## Manual tests - four requested categories

[MANUAL_TESTS.md](MANUAL_TESTS.md) defines **24 manual test cases**: six Boundary tests, six Size limit tests, six Structure tests and six Format validity tests. Each has steps, expected results, story IDs and fields for status, actual results, tester, date and evidence. The [CSV log](docs/manual/MANUAL_TEST_LOG.csv) and [JSON log](docs/manual/MANUAL_TEST_LOG.json) start **Not run**. No human manual passes or human study results are asserted. Automated results above are recorded separately.

## Remaining acceptance checks and limits

- Story #28 is implemented and its request, cached-link, failure, unchecked-item and redirect contracts are tested with HTTP mocks. A live Instacart development key is still required to verify a real shopping link. Missing configuration fails clearly while keeping the grocery list usable. This integration never places an order. Unit names not mapped by the adapter remain display text for the shopper to review and adjust.
- Story #8's skippable, short wizard is implemented and browser-tested; a human's three-minute completion target is not established by an automated run.
- Native Windows UI execution, live Anthropic quality/cost, real SMTP delivery, production load and real product-label/price suitability remain environment-dependent checks. Linux browser/API behavior is not reported as Windows or human acceptance.
- Unknown/unsupported dietary notes and unmet soft nutrition/cooking goals remain visible for review; encoded ingredient checks do not certify allergies, cross-contact, nutrition adequacy or retailer prices.
- Test provenance: these additions and manual procedures were AI-assisted. No human-authorship percentage has been inferred from the existence of a manual procedure.

## Reproduce

```bash
python -m pip install -r requirements-dev.txt
python -m coverage run --source=app -m pytest -q
python -m coverage report --fail-under=90
npm ci
npx playwright install chromium
npm run test:e2e
npm run test:e2e:audit
python -m scripts.audit_correctness --repeats 3
```

Use a disposable database/account for manual/provider tests. The verification environment used no Anthropic key and no real Instacart key. The local browser runner used a temporary Chromium binary because the standard browser CDN download was unavailable; no extra Chromium package was added to project dependencies.

## Import into your existing Windows checkout

Place the supplied KS_All_Stories.bundle directly on your OneDrive Desktop, then run in Git Bash:

```bash
cd "$HOME/OneDrive/Desktop/KS_LLM" &&
git switch KS_Work &&
git fetch "$HOME/OneDrive/Desktop/KS_All_Stories.bundle" KS_Work &&
git merge --ff-only FETCH_HEAD &&
git push origin KS_Work
```

Keep your existing local `.env`, `.venv` and database. The archive excludes those files. If Git reports local changes or divergent history, stop and resolve it; no reset or force push is required by these instructions. This package adds no schema migration or runtime dependency beyond the existing HTTP client; coverage is a development dependency.
