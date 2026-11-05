# Manual acceptance tests - group 2: stories #7-#11

Execution type: Manual. These are authored test procedures, not automated test passes. A human has not executed this sheet.

Preconditions: a disposable local account/database, application running without an Anthropic key, browser developer tools available. Use developer fixtures only in a disposable environment. Record date, browser/version, commit and screenshots when executing.

## M02-01 - Boundary tests: Pantry quantities

Stories: #7-#11

**Steps:** Add rice with quantity 0, then 1000000, then 1000001, then NaN using developer tools. Reload after each attempt.

**Expected:** Zero and the maximum finite quantity save; over-limit/nonfinite inputs are rejected without changing stock.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M02-02 - Size limit tests: Pantry name, unit and entry caps

Stories: #7-#11

**Steps:** Try names of 100/101 characters, units of 20/21 characters, and a 201st distinct pantry entry after reaching 200. Existing entries may still be updated.

**Expected:** Maximum-length names/units save; longer values and a new 201st entry are refused, never silently truncated. Updating an existing entry still works.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M02-03 - Structure tests: Minimal onboarding and full-week structure

Stories: #7-#11

**Steps:** For a new account, enter only a valid budget, leave optional diet/goal/notes/pantry blank, finish the wizard, and open every day and a full recipe. Record onboarding duration separately if a human performs it.

**Expected:** Seven days have breakfast/lunch/dinner (21 slots), with ingredient quantities and preparation steps. No optional answer is required. The three-minute human setup criterion is NOT inferred from software timing.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M02-04 - Format validity tests: Malformed provider payload

Stories: #7-#11

**Steps:** In a developer test session, use tests.test_plan.Scripted as a dependency override to return meals as a string, a blank recipe name, 22 meals, 31 steps, or 51 ingredients; request generation for each. Do not add a production debug endpoint.

**Expected:** The schema rejects malformed/oversized responses, bounded retries show a useful error, and the last valid plan remains available.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.
