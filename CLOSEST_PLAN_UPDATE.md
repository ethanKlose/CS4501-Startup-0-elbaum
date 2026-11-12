# Closest-plan generation and calendar status

## Result

The production default now returns the closest safe complete plan it finds, with
explicit budget, calorie, protein and cooking-time differences. It no longer
rejects a whole plan merely because shopping exceeds the requested budget.
The requested budget and goals stay unchanged in the saved plan and UI.

The screenshot showed an old $75 plan after a failed $125 request, rather than
a browser cache problem. A saved-preferences signature now identifies that state:
the calendar displays **Previous preferences** and a notice until a new plan is
made. A new approximate plan displays **Closest available plan**, actual values,
a daily breakdown and warnings. Shopping totals say **over budget** when needed.
Previously generated plans remain accessible in History.

## Search and reliability

One configured-provider planning attempt is compared with three local catalog
searches, including relaxed search budgets. All candidates are assessed against
the ORIGINAL user settings. Ranking balances budget overspend, calorie distance,
protein shortfall and scheduling conflicts; variety breaks ties. Search is bounded,
so closest found does not mean mathematically optimal. The model adapter may make
its existing bounded missing-slot repair requests inside that planning attempt.
Local candidates do not use API tokens. No paid provider was called for this work.

If the provider is unavailable, returns malformed data or invents ingredients,
the local catalog can still supply the current plan. The UI and saved metadata
identify the selected source, rather than labeling a fallback as AI-generated.
Recipe content must match the trusted catalog or an unchanged pin. Food exclusions,
kitchen compatibility, complete coverage, cost integrity and known prices remain
mandatory. A plan is never fabricated around an allergy or missing data.

Requests outside the app's supported range ($30–$10,000; 1,200–4,500 kcal/day)
return to Preferences with an explanation. A genuinely unsupported safe-food/
kitchen/pin combination also returns there rather than inventing a usable plan.
These are app/catalog limits, not a claim that the user's constraints are
medically unreasonable or mathematically impossible. Full-day nutrition cannot
be verified when outside meals are unknown; the UI labels the measured values
as planned nutrition. Existing plan/inventory changes roll back on rejection.

Swaps and skipped days recompute the deviations. Compatible pins retain their
existing behavior. There are no database migrations or new credentials to add.
`BEST_EFFORT_PLANNING` defaults to `1`; setting it to `0` explicitly restores the
older strict-budget policy. Legacy regression fixtures select strict mode to keep
checking that supported compatibility contract. The new integration tests select
the production best-effort policy and use actual routes and migrated databases.

## Evidence

- 805 legacy strict-policy cases passed in the full regression run.
- 12 production-policy integration cases passed across final focused runs.
- 44 DOM cases passed.
- A prior full-run banner-attribution assertion was corrected and passed in the
  final feature rerun. The entire combined suite was not rerun after that fix.
- Real-browser testing was not performed for this follow-up.

An actual offline example with $125, 140g protein, 2,500 kcal, 60 cooking minutes
per day and seed 1729 produced 21 meals: **$123.42 shopping, 2,435 kcal/day average,
and 143.5g protein/day average**. Daily gaps remain visible. This is an engineering
example using demo prices, not a live retailer quote or human study. Your other
preferences, pantry and prices can change the result. The full example is included
in the download.

To run the new policy checks without spending API balance:

```bash
.venv/Scripts/python.exe -m pytest -q tests/integration/test_closest_plan.py
npm run test:ui
```
