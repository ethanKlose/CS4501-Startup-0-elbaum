# Beta planning and nutrition preferences

## Changes

- Public branding (navigation, login/register, landing page and API title) says
  Beta. This label is not a claim that every roadmap item is complete.
- Protein and calorie goals are independent selections. Select either, both, or
  neither. Clearing one goal does not clear the other.
- Protein has a 20–300g slider and a matching whole-number field, adjustable in
  1g increments. The input is a **daily minimum target**, not a portion multiplier.
  Both targets are saved in the profile, sent to the configured generator, saved
  with the plan and checked on regeneration, swaps and rescheduling.
- A custom protein target is checked against each planned day's total and the
  daily average. Calorie tolerance remains 10% over the week and 30% per day.
  These remain best-effort nutrition goals: misses are shown for review, not
  silently called successful. The fixed catalog may not be able to meet every
  combination. Meals eaten elsewhere make full-day nutrition unverifiable.
- Four planning sections replace the disconnected forms: Budget & goals, Food
  preferences, Your week, and Your kitchen. Budget presets, equipment, cooking
  days and navigation use consistent, aligned controls.
- A seven-day meal grid marks meals eaten elsewhere. Advanced meal times and
  cooking windows are expandable. The summary updates as you edit.
- One save commits the survey, kitchen, campus meals and timing together. A
  validation failure rolls everything back and preserves typed inputs in the
  error view. Client validation opens the relevant step before focusing a field.
  Pantry edits remain separate and are labeled accordingly.
- Without JavaScript, all sections remain editable with the normal server save.

Existing single-goal HTTP requests remain supported. Existing saved plans without
`protein_target` retain the legacy 75g high-protein interpretation and their
original nutrition warnings until explicitly edited/rescheduled. Changing current
preferences does not rewrite plan history.

## Install

The downloadable `KS_Beta_Planning_Update.zip` contains:

- `apply_update.py`: checks your local repository and applies the matching patch.
- `KS_Beta_Planning_Update.patch`: incremental update after the Kroger UI patch.
- `KS_Beta_Planning_With_Kroger_UI.patch`: includes that preceding UI patch for
  installations that only applied `KS_Kroger_Integration.patch`.

Stop the server with Ctrl+C. Extract the ZIP to Downloads so `apply_update.py` is
inside `Downloads/KS_Beta_Planning_Update`. Run in Windows Git Bash:

```bash
cd ~/OneDrive/Desktop/KS_LLM
.venv/Scripts/python.exe "$HOME/Downloads/KS_Beta_Planning_Update/apply_update.py"
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

The installer checks both patch variants before making changes. If neither fits,
it stops without applying a patch. It does not switch branches, commit, push,
read `.env`, call a model or change account credentials. Stop if it reports an
error. The base Kroger integration must already be installed.

Before the first restart, keep a backup of your current database. For the default
setup, stop the app and copy `platejoy.db` to a backup file. If you use another
database URL, back up that database instead. Startup automatically runs the
non-destructive Alembic migration `0002_protein_target`: it adds a nullable integer
column to profiles, without dropping tables or resetting data. Do not delete the
database to install this update. The migration intentionally blocks downgrade to
avoid discarding saved custom targets.

Open <http://127.0.0.1:8000/survey> and press Ctrl+F5. Existing plans keep their
saved settings; generate or regenerate a plan when ready to apply your new goals.
No `.env` changes or new runtime dependencies are needed. Editing the slider and
goal controls makes no AI calls. Actual plan generation uses the existing model
and retry limits; this update does not run paid live tests automatically.

## Validation

Final run: **771 Python tests passed**, plus **24 JavaScript DOM tests passed**.
Python application statement/line coverage is **95.50%**
(3435 of 3597 measured statements).
This update adds 33 Python cases and 14 DOM cases. The full Python suite emitted
1106 existing deprecation warnings and completed in 216.87 seconds.

Exact final counts and coverage are recorded in
`docs/evidence/beta-planning/validation.json`.

New Python checks cover target boundaries, independent selection/clearing,
invalid/nonfinite values, full-form rollback, error readback, database migration,
legacy defaults, simultaneous target checks, external meals, saved history and
regeneration. A provider-boundary test exercises the production prompt and catalog
hydration with a controlled response, without claiming live model quality.

New JavaScript tests render the actual application route into an isolated DOM and
run the production JavaScript. They exercise slider/number synchronization, both
selected goals, inactive field submission, preset states, navigation, validation
of hidden steps, advanced details, the meal grid and unified form boundaries.

The browser smoke workflow has been updated for the unified save. Native Chromium
launch is blocked in the authoring environment, so that workflow was not run
locally for this update. Static desktop and phone-width layouts were inspected;
DOM tests and static renders do not establish browser layout correctness.

Reproduce automated checks:

```bash
.venv/Scripts/python.exe -m pytest -q
npm ci
npm run test:ui
```

Suggested local visual checks (not recorded as executed by a person):

1. Select both targets. Set protein to 137g with the number field and confirm the
   slider follows. Move the slider and confirm the field and summary follow.
2. Save, reload, and verify both targets remain selected. Clear just one, save,
   and verify the other remains. Clear both to return to no nutrition goal.
3. Mark Wednesday lunch as Elsewhere and deselect unavailable kitchen equipment.
   Save once, reopen both sections and confirm every choice was preserved.
4. Try an out-of-range protein number and invalid cooking window. Check that the
   field is shown and that the rest of your saved preferences did not change.
5. Check phone width, keyboard focus, dark theme, and the aligned meal grid.
6. Generate only when ready to use your configured model. Inspect any nutrition
   warnings and ensure a previous plan still shows its original settings.
