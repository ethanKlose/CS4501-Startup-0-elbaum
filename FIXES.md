# KS_LLM fixes

Based on `alpha-mvp` at `263ef2b2fbc8628844d2a1ca3ab152027eec3817`.
Work branch: `ks/fixes`. Each fix or enhancement has its own commit. Nothing was pushed to GitHub.

| Commit | Change |
| --- | --- |
| `e9849a2` | Fix dietary exceptions without hiding restricted ingredients |
| `e97884e` | Validate the entire pinned recipe during regeneration |
| `96abfab` | Preserve completed meal history by restricting swaps |
| `fc2b0bd` | Reject nonfinite survey and ingredient numbers safely |
| `2b12040` | Restore grocery progress when saving a check-off fails |
| `cae69ea` | Surface dependency failures during local setup |
| `06bde84` | Keep the Compose database on the persistent data volume |
| `c9d767d` | Schedule cooking before each batch's earliest mealtime |
| `188b2ec` | Start plans in a future week and add explicit week advancement |
| `1f50a99` | Reconcile pantry stock from confirmed purchases and cooked meals |
| `aefd741` | Show whether plans use the offline demo or configured AI |
| `7704c61` | Add an agenda view and explain plan replacement before regenerating |
| `6e92222` | Keep swapped-plan settings and check-in dates consistent |
| `ac0122e` | Run the complete browser smoke flow locally and in CI |

The final documentation commit adds this map and the extraction instructions.

## Validation

- Full Python suite: **396 passed** in 53.74 seconds on Python 3.12. The remaining warnings are deprecations in the existing stack.
- Browser smoke flow: passed signup, survey, automatic generation, demo mode, agenda persistence, exact demo pin retention, completed-meal protection, planned-meal swap, day skip/restore, grocery check-offs and rollback of checkbox/count/bar, pantry editing, budget validation, theme, phone/tablet overflow checks, meal dialog, check-in closure, login/logout and explicit week advancement.
- Regression cases cover a vegan chicken-broth response being rejected, modified pinned recipe content being rejected, extreme numeric inputs returning validation errors, no pantry double-counting, actual purchase snapshots, partial-stock consumption, idempotent settlement, rollback on failed regeneration and stale-tab protection.
- `make setup` was checked with an intentionally failing Python executable and correctly returned an error.
- Python compilation, JavaScript syntax, Git whitespace checks and CI/Compose YAML parsing passed.
- No paid/live model calls were made. Live Anthropic generation and actual Docker container recreation remain unverified. The CI workflow is included but has not been run on GitHub.

## Behavior decisions

- New plans start next Monday; a stored week date keeps the calendar consistent. Sunday prep is omitted if that Sunday is already today. Regeneration keeps the displayed future week, while Plan next week advances dates and clears one-week skips.
- Only planned, unrated meals can be swapped. Completed history is retained.
- Check-offs record actual quantities. Check-in applies current pantry plus confirmed purchases minus cooked ingredients once. Buying the entire list requires an explicit checkbox. Closing a plan disables status and grocery changes; feedback and ratings remain editable.
- Successful regeneration archives and settles the old plan; failure rolls inventory changes back.
- These fixes store new metadata in the existing plan settings JSON, so an alpha database matching the starting commit needs no schema reset.

## Package

The ZIP contains the complete `KS_LLM` working tree and `.git` directory, including the original repository history and the new commits. It excludes virtual environments, dependency folders, local environment files, SQLite databases, caches and test screenshots. `origin` points to the supplied GitHub URL.
