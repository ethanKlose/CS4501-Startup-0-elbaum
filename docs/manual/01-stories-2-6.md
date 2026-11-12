# Manual acceptance tests - group 1: stories #2-#6

Execution type: Manual. These are authored test procedures, not automated test passes. A human has not executed this sheet.

Preconditions: a disposable local account/database, application running without an Anthropic key, browser developer tools available. Use developer fixtures only in a disposable environment. Record date, browser/version, commit and screenshots when executing.

## M01-01 - Boundary tests: Budget and nutrition boundaries

Stories: #2-#6

**Steps:** Submit budgets 29.99, 30, 10000, 10000.01; submit calorie goals 1199, 1200, 4500 and 4501. Reload after each.

**Expected:** Only the documented budget range 30-10000 and integer calorie range 1200-4500 save; failures leave saved answers unchanged.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M01-02 - Size limit tests: Preference note lengths

Stories: #2-#6

**Steps:** Type/paste 500 characters into the preference note and save. Use browser developer tools to remove maxlength, submit 501 characters, then reload.

**Expected:** 500 characters save; 501 returns an inline field error; previous note remains intact.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M01-03 - Structure tests: Complete weekly availability and diet state

Stories: #2-#6

**Steps:** Set different minutes for each of seven days, select vegan and nut allergy, save and reload; clear both checkboxes and save again.

**Expected:** All seven weekdays retain the correct values in order; clearing restrictions explicitly clears both; optional sections remain skippable.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M01-04 - Format validity tests: Reject rounding and unknown restrictions

Stories: #2-#6

**Steps:** Using browser network tools or an HTTP client, submit minutes_0=15.9, calorie_target=1200.9, and restrictions=made_up with restrictions_present=1, one at a time. Then submit the note I only eat chicken and generate.

**Expected:** Invalid numeric formats and unknown choices show errors rather than truncation or silent removal. The readback enforces chicken-only meat; generated catalog ingredients contain no other meat or seafood.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.
