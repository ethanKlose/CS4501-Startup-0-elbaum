# Manual acceptance tests - group 5: stories #22-#26

Execution type: Manual. These are authored test procedures, not automated test passes. A human has not executed this sheet.

Preconditions: a disposable local account/database, application running without an Anthropic key, browser developer tools available. Use developer fixtures only in a disposable environment. Record date, browser/version, commit and screenshots when executing.

## M05-01 - Boundary tests: Partial and full pantry deductions

Stories: #22-#26

**Steps:** For a grocery ingredient, record its required quantity N; add N-1, N, and N+1 in matching units, and then try the same number in a different unit.

**Expected:** The list shows only the shortfall, drops fully covered items, and never converts unrelated units. Estimated costs adjust with the shortfall.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M05-02 - Size limit tests: Repeated ingredient consolidation

Stories: #22-#26

**Steps:** Generate a week with repeated recipes; inspect the grocery list after a single-meal swap and a regeneration with pins.

**Expected:** Each normalized name/unit combination appears once; quantities sum all active meal requirements without duplicate rows or stale swapped ingredients.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M05-03 - Structure tests: Sections, snapshots and swap isolation

Stories: #22-#26

**Steps:** Capture the week, pin one meal and swap another. Compare all other meal names, amounts, steps and slots. Review each grocery section and current verification panel.

**Expected:** Only the requested meal changes; pins remain byte-for-byte equivalent in normalized recipe content; the complete plan is revalidated and each grocery item appears in exactly one store section.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M05-04 - Format validity tests: Canonical ingredient units and adversarial revalidation

Stories: #22-#26

**Steps:** Use a developer fixture containing RICE / CUP and rice / cup. Then return a fixture with one duplicate slot and one missing slot on regeneration.

**Expected:** Names/units consolidate canonically; duplicate/missing coverage is rejected and the last valid plan is not overwritten.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.
