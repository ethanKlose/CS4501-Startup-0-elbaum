# Planner quality and preference progress update

Built from pushed `KS_Work` commit `aa91944` (Add red teaming preparation
playbook). No unpublished Claude edits were used. No paid provider was called.

## What changed

| Area | Previous behavior | Updated behavior |
| --- | --- | --- |
| Planning objective | Prompt asked for only 5–8 recipes and spending well under budget; repeats and cheap ingredient reuse dominated. | Nutrition targets, preferences, variety, produce and workable preparation guide selection. Budget remains a hard ceiling. |
| Budget retries | A previous budget miss could leave the provider stuck with the cheapest two dishes per slot. | Seeded shortlists retain inexpensive, nutrient-fit and varied options. No sticky cheapest-only mode. |
| Catalog | 54 recipes using 73 ingredients. | 110 recipes using all 118 sourced ingredients, with actual quantities, steps and computed nutrition. |
| Reference prices | Median costs were recomputed from recipes, so adding recipes could change old prices. | 121 explicit package offers, preserving the previous 76 estimates. User-entered prices still override them. |
| Price context | Provider mostly saw portion costs. | Shortlisted dishes include ingredient overlap and a whole-package estimate for one serving after pantry deductions. These estimates are not additive basket totals. |
| Improvement | A valid cheap plan could stay repetitive. | A bounded local improvement pass considers recipe swaps without extra AI requests and rechecks diet, budget, coverage, pins and cooking deadlines. |
| Swapping | A general shortlist could miss a basket-compatible replacement when other meals were pinned. | The bounded one-slot fallback searches all eligible recipes, keeping the other meals unchanged. |
| Regeneration | The same small set could recur. | Different seeds explore the expanded catalog; recent unpinned dishes receive a soft avoidance preference. |
| Pantry add/delete | Whole-page redirect discarded preference edits. | Only the pantry list updates. Validation/network errors preserve the rest of the form; ambiguous network results offer a read-only refresh. |
| Other progress loss | Reloading or visiting another page lost unsaved preferences. | Per-account, per-tab drafts restore values, selections, current step and expanded sections. Conflicting saved settings require a Restore/Discard choice. |
| Save then refresh | A success marker could discard a new draft typed just after saving. | The marker is consumed once and removed from the URL. Logout also prevents drafts from being recreated by page-exit events. |
| Budget display | The headline showed portion cost, which differs from buying full packages. | The main figure is the saved shopping estimate; portion cost and variety are shown separately. Swaps and skipped days recompute the estimate. |

## How the planner now works

1. Interpret saved preferences and exclude incompatible diet, ingredient,
   equipment and skill choices before proposing meals.
2. Offer up to 18 dishes per slot, balanced across cost, nutrient fit and variety.
   A budget retry keeps alternatives instead of collapsing to two dishes.
3. The configured model selects names and slots. Trusted server data supply
   ingredients, quantities, steps, nutrients and costs. The offline engine uses
   the same catalog and validation rules.
4. Validate coverage, ingredient totals, dietary restrictions, budget, pins and
   cooking deadlines. Invalid provider output is still rejected and fed back.
5. For an already hard-valid plan, evaluate at most 420 local alternatives over
   two passes. Cheap scoring ranks proposals; only the best few per slot receive
   full scheduling/validation. Accept improvements without worsening warnings.
6. Save the plan, verification results, shopping estimate and variety metrics.

The 75–95% preferred spending range is a **weak preference**, not a required
minimum or a guarantee. Pantry stock, partial weeks, dietary limits and schedule
constraints can justify spending less. More expensive meals are not automatically
better. Selected calorie/protein goals take priority over spending and variety.
A 2,000 kcal reference used when no goal is selected is only a scoring heuristic,
not a medical recommendation or a pass/fail target.

## Measured comparison

These are actual **offline engineering runs**, not participants, live-model
results or retail price measurements. The same 12 configurations were run before
and after: budgets $50/$100/$150, standard/vegan diets, seeds 1/23, a full week,
45 cooking minutes per day, no pantry, and a selected 2,000 kcal daily target.

| Budget | Before: distinct recipes | After: distinct recipes | Before: ingredients | After: ingredients | After: package estimate |
| --- | --- | --- | --- | --- | --- |
| $50 | 3 | 4–5 | 8–9 | 13–17 | $49.10–$49.47 |
| $100 | 6 | 9–12 | 16–21 | 27–35 | $96.86–$98.76 |
| $150 | 6 | 14 | 16–21 | 39–42 | $117.63–$127.35 |

All 12 updated configurations passed every encoded hard and soft check. The
$50 cases still repeat some dishes seven times; the limited budget makes variety
harder. This is a bounded search, not a proof of an optimal or universally
feasible plan. A near-full shopping basket can also leave no affordable single-meal
replacement with the other 20 meals pinned; the app must keep the old plan rather
than exceed the budget. Full records are in `docs/evidence/planner-quality/before.json`
and `after.json`; the baseline is `aa91944`.

A separate 20-configuration stress run accepted 18 plans, with 16 meeting all
encoded checks. It retained honest limitations: the $30 case and an evening-only
cooking-window case found no hard-valid plan; a zero-minute-every-day case needed
cooking-time review, and dining-hall meals prevented full-day nutrition
verification. Those results are in `stress.json`. A failed search is not proof
that the user's constraints are impossible. This update does not claim those
remaining search/knowledge limits are solved.

## Verification and commands

Run from the repository folder in Windows Git Bash. These use the offline engine
and controlled HTTP provider transports; they do not spend your API balance.

```bash
.venv/Scripts/python.exe -m pytest -q
```

```bash
npm ci
npm run test:ui
```

```bash
.venv/Scripts/python.exe -m scripts.benchmark_planner_quality --output test-results/planner-quality.json
```

For the broader stress matrix:

```bash
.venv/Scripts/python.exe -m scripts.audit_correctness --repeats 1 --output test-results/planner-stress.json
```

For real browser verification on your computer:

```bash
npx playwright install chromium
npm run test:e2e
npm run test:e2e:audit
```

Both browser scripts start their own isolated temporary database and explicitly
blank both provider keys. Here Chromium could not start because the environment
blocked its required local socket. The app server started, but these browser
workflows are **not reported as passed**. Route/database tests and DOM tests use
the real application code; controlled provider/network responses are not evidence
of live OpenAI, Google or Kroger availability.

The USDA import was also checked to reproduce the ingredient and package-price
files byte for byte from the documented ZIP. See `DATA_SOURCES.md`.

## Quick local review

1. Restart the app. On Preferences, use a $100 or $150 budget, choose the desired
   protein/calorie goals, save, and **regenerate**. Existing saved weeks retain
   their recipes until regenerated. Inspect variety, nutrition warnings, groceries
   and the package-price breakdown. Regenerate again to try another seed.
2. Without saving, change the budget, protein/calorie amount, dietary choices,
   cooking times and campus meals. Move to another step, expand Pantry, then add
   and remove an ingredient. The page, draft fields and step should stay intact.
3. Visit Grocery and return to Preferences, then refresh. Your draft should
   restore. Save it, make another edit immediately, then refresh again: that new
   edit should also restore. Discard draft should return to saved settings.
4. With two tabs, save different preferences in the other tab, then return/reload
   the first. It should ask which version to keep, rather than silently apply
   an older draft. Sign out and sign back in: old drafts should be cleared.
5. Temporarily switch your browser offline before a pantry change. Your preference
   edits should remain; after reconnecting, use **Refresh pantry list** before
   retrying to avoid duplicating an uncertain action.

These five procedures are provided for local manual review; they are not claimed
as human-executed tests here. Draft persistence requires browser session storage
and JavaScript. If storage is blocked, the page still works and pantry AJAX still
preserves current-page fields, but reload recovery is unavailable. With JavaScript
fully disabled, pantry forms still work by redirect; save preferences first.

No new environment variables or database schema changes are needed. Keep your
existing private `.env` and database. No changes have been pushed by this update.
