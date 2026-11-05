# Correctness validation

Human planning-time savings and app-versus-questionnaire preference are deferred.
This work covers software correctness, a review mechanism and reproducible local evidence.

## Automated validation

Run from the repository with its virtual environment:

```bash
python -m pytest -q
python -m scripts.audit_correctness --repeats 3
npm run test:e2e
npm run test:e2e:audit
```

On Windows Git Bash, use `.venv/Scripts/python.exe` in place of `python`.
For browser tests set `export PYTHON="$PWD/.venv/Scripts/python.exe"` after installing Node dependencies and Playwright Chromium.

The correctness CLI emits `evals/audit-after.json` and `.csv`: 20 configurations,
three fixed seeds, accepted plans, fully satisfied checks, warnings and errors.
Seeds/configurations are engineering cases, not enrolled students. Runtime seconds
measure software response time, not human planning-time savings.

The browser audit covers the original dietary request, the feasible $40 case,
outside meal positioning, early/late calendar bounds, phone/tablet widths,
unmet goal labels and correctness feedback. Pytest additionally freezes dates to
exercise elapsed pins and tests valid late cooking windows.

## Reviewing a real plan

Open `/feedback`, inspect the linked plan and choose Yes, No or Not reviewed yet
for whether it meets all constraints. If No, mark the affected constraint types.
The submitted plan ID is checked for ownership and retained even if a newer plan
is generated before submission. Automatic check results are stored separately
from the person's answer. These are student self-reviews, not an independent
investigator's correctness judgments.

Consented categorical results are included in `python -m scripts.export_study`.
An owner can get a correctness-only summary with:

```bash
python -m scripts.export_study --correctness-only
```

The summary counts the latest consented response per account once, preserves
unreviewed/missing outcomes, and leaves the 15-of-20 threshold undecided until
20 accounts have reviewed outcomes. It does not invent enrollment or responses.
Separate accounts still need to be matched to actual participants by the study
organizer; account count alone does not verify participant identity.

For independent correctness review, an organizer should evaluate each original
budget, dietary request, kitchen, schedule, meal coverage and goal against the
resulting recipes and grocery basket, recording failed constraints separately.
Do not use the app's own check status as the independent ground truth. Record
unverifiable outside-meal nutrition and missing data explicitly. Recruiting real
participants and collecting independent reviewer judgments remain human tasks.

## Limits

Prices are demo estimates unless replaced by local receipt prices. Nutrients use
the documented catalog mappings. Equipment checks infer appliances from recipe
instructions. Live Anthropic behavior, billed costs, real mail delivery and native
Windows execution require their own configured checks. No time-savings or
preference outcomes are claimed by this implementation.
