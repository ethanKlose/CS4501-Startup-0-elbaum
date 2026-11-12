# Meal variety correction

Variety now contributes directly to the final plan score. It is measured for
breakfast, lunch and dinner separately, and repeat counts also span meal types.
Default soft targets are three breakfast recipes, three lunch recipes and four
dinner recipes, usually at most three occurrences and two consecutive days of a
dish. Targets scale down for partial weeks, limited eligible recipes and pins.
They never become reasons to withhold an otherwise safe complete plan.

A bounded local pass diversifies each safe AI/catalog candidate before selection.
It evaluates at most 320 replacements per candidate over two passes, using the
approved, price-adjusted catalog. It preserves pins, dietary exclusions, equipment,
coverage, trusted quantities/nutrients/steps and cost arithmetic. No additional
AI requests are made by diversification. Small calorie/protein differences inside
scoring bands do not automatically beat a much more varied week.

Repair cannot worsen existing calorie deviations beyond a 10% daily band or
protein shortfalls below a 95% daily floor. Existing larger shortfalls cannot be
made worse. Selection weights budget overspend more strongly and repair cannot
increase shopping beyond the larger of its starting total or 105% of the requested
budget. This small reviewable allowance follows the existing best-effort policy;
all actual overspend and nutrition gaps remain visible, and no shopping order is
submitted automatically. Constrained cases can still repeat, with a variety notice.

For outside meals, selection uses an equal-per-slot share as a heuristic for the
meals actually planned. It does not invent outside-meal nutrients or claim full-day
goals are verified. Remaining uncertainty stays visible. The calendar now shows
per-meal choice counts and a Meal variety check, so diverse dinners cannot hide
seven identical breakfasts.

Validation: 11 focused variety tests passed on the final code; 49 related planner,
provider, catalog and closest-plan cases passed during development; 44 DOM tests
passed. The final small cross-meal repetition change was covered by the focused
variety rerun; the full Python suite was not rerun. Real-browser testing was not
performed for this follow-up. No paid API calls, environment changes or migrations.

Checks include the $125/140g/2500kcal case with two outside dinners, calorie/protein
protection, dietary restrictions, pins, partial weeks, a one-choice-per-slot catalog,
a $30 budget, whole-week repeat counts and exactly one controlled provider attempt.
The repeated seed test reaches at least 3/3/4 choices where feasible. The outside-
meal regression requires at least three breakfast and lunch choices, with at most
four repeats in those slots, while retaining honest nutrition warnings.

After installing, restart the app, hard-refresh Preferences and regenerate the
week. Existing saved calendars are not rewritten automatically.
