# Local audit fixes on KS_Work

Based on the version already pushed to GitHub: `359263f`.
Human time-savings and preference outcomes are deferred. No participant results
were invented or collected during this implementation.

## Fixed

| Finding | Result |
| --- | --- |
| Dietary notes missed | Comma/or/and lists, repeated negations, vegan/vegetarian statements and daily minute limits are parsed. Explicit local constraints survive an incomplete model extraction. Unsupported notes carry visible review notices. |
| False $40 budget rejection | A whole-package basket search supplies a cheap valid fallback while preserving diet, kitchen, prices, pantry, pins and scheduling checks. Failed searches are no longer presented as proof of impossibility. |
| Late cooking rejected | The scheduler honors actual meal deadlines and explicit late windows, retaining the default cutoff for ordinary schedules. |
| Past pins block planning from today | Elapsed, skipped and outside meal slots are removed from the new required pins after start-time filtering; archived meals remain intact. |
| Unconditional Verified label | A scoped checks panel distinguishes passed, unmet, unrequested and missing historical rules. Goals or notes needing review change the headline status to Needs review. Public guarantee/time claims were narrowed. |
| Outside meals and late calendar bounds | External events receive proper time/lane positioning. Grid bounds include early meals, late meals and events crossing midnight. |
| Correctness not recorded | Feedback records an owned plan, an explicit Yes/No/Not reviewed result, failed constraint categories and a separate automatic-check snapshot. Timing and spending fields can be left blank. |
| Repeated feedback could inflate a study | The correctness-only summary counts the latest consented result per account once and leaves incomplete 15-of-20 results undecided. These remain self-reviews, not independent reviewer judgments. |
| Retry-After mismatched rate window | The header reports the actual remaining counter-window duration. |

## Reproducible correctness results

| Metric | Before | After |
| --- | --- | --- |
| Configurations | 20 | 20 |
| Seeds per configuration | 3 | 3 |
| Plans accepted | 54/60 (90%) | 57/60 (95%) |
| Every encoded check satisfied without warnings | 51/60 (85%) | 54/60 (90%) |
| Human participants | 0 | 0 |

The three remaining rejected runs are $30 budgets. The search did not find a
valid basket for them; this is not a mathematical impossibility proof. The three
accepted warning cases are plans with dining-hall lunches: complete daily
nutrition cannot be verified without those outside meals. Warnings remain visible.

The original adversarial dietary-note failures, valid late-window case, elapsed
pin case, $40 case and calendar geometry failures now have regression coverage.
The new browser audit additionally submits a correctness review with all timing
and spending fields blank, using actual browser form serialization.

Raw after-results are in `evals/audit-after.json` and `.csv`. They are engineering
cases for the offline demo engine, not student success rates. Latency in these
files measures software generation, not time savings against a questionnaire.

## Validation

Final Python suite: **453 passed, 620 deprecation warnings, 87.32 seconds** on Python 3.12.14.
The existing full browser smoke workflow and the added audit-regression browser
workflow both passed with no JavaScript exceptions. Chromium 153.0.8010.0 was
used with Playwright 1.62.1 and a disposable SQLite database.
Python compilation, JavaScript syntax and Git whitespace checks also passed.
See `CORRECTNESS_VALIDATION.md` for commands and the owner-operated correctness
summary. Existing consented numeric exports remain compatible with older entries.
Legacy plans without the saved diet/price snapshot show Not recorded rather than
being retroactively labelled as verified.

## Remaining configuration-dependent checks

Live Anthropic quality/cost, real SMTP delivery, native Windows execution and
deployment load tests still need those environments. Built-in prices remain demo
estimates; nutrition uses the documented source/portion mappings. Equipment
requirements are inferred from recipe instructions. Neither the automated checks
nor the feedback form constitute an independent real-world food-label audit.

Use `APPLY_AUDIT_FIXES.md` to import the bundled separate commits into the existing
local KS_Work checkout and push from your own authenticated terminal if needed.
These fixes add no new dependencies or schema migrations.
