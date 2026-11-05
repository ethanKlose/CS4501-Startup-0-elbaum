# Manual acceptance tests - group 4: stories #17-#21

Execution type: Manual. These are authored test procedures, not automated test passes. A human has not executed this sheet.

Preconditions: a disposable local account/database, application running without an Anthropic key, browser developer tools available. Use developer fixtures only in a disposable environment. Record date, browser/version, commit and screenshots when executing.

## M04-01 - Boundary tests: Late and zero-minute cooking

Stories: #17-#21

**Steps:** Set Wednesday minutes to 0 and select Sunday preparation. Enter meal times 06:00/13:00/22:00 and valid cooking windows; generate and inspect assignments and calendar bounds.

**Expected:** No active cooking exceeds a daily capacity or misses a deadline. Early/late/outside events fit the grid. Unmet soft goals/time requirements remain visible as Needs review.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M04-02 - Size limit tests: Cooking-window count

Stories: #17-#21

**Steps:** Submit eight valid nonoverlapping windows for one day, then nine windows or a field longer than 127 characters.

**Expected:** At most eight windows are accepted; oversized/count-over-limit input returns 400 and does not replace the saved schedule.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M04-03 - Structure tests: Skip, restore, pin and regenerate

Stories: #17-#21

**Steps:** Pin a future meal, skip an unused future day, regenerate, restore that day and regenerate again. Open a recipe and return to the calendar. Close the plan via check-in and try pinning an old meal.

**Expected:** The pin stays identical; skipped slots and groceries disappear; restored slots return after regeneration; detail links work. Closed-plan pin controls are absent and a direct pin request returns 409.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M04-04 - Format validity tests: Strict clock syntax

Stories: #17-#21

**Steps:** Try 7:00, 07:0, 24:00, 12:60, overlapping/reversed windows and valid 00:00/23:59 endpoints.

**Expected:** Only HH:MM clocks with valid hours/minutes and ordered, nonoverlapping windows save. Invalid submissions preserve prior values.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.
