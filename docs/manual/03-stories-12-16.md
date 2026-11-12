# Manual acceptance tests - group 3: stories #12-#16

Execution type: Manual. These are authored test procedures, not automated test passes. A human has not executed this sheet.

Preconditions: a disposable local account/database, application running without an Anthropic key, browser developer tools available. Use developer fixtures only in a disposable environment. Record date, browser/version, commit and screenshots when executing.

## M03-01 - Boundary tests: Pantry-aware spending

Stories: #12-#16

**Steps:** Generate with no pantry, record the package estimate, then add enough matching-unit pantry stock to cover ingredients and regenerate using the same saved requirements. Also try a budget below all known recipe portions using a developer fixture.

**Expected:** Both remaining-portion and whole-package costs are checked after pantry deductions; owned food is not charged again. Failure explains a budget issue or failed search without claiming all possible menus are impossible.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M03-02 - Size limit tests: Bounded validation failures

Stories: #12-#16

**Steps:** Return an invalid developer fixture with many malformed meals or missing fields; generate and inspect the message and browser cookies.

**Expected:** Error output is bounded to the schema error limit; no giant error/stack trace or corrupted session cookie; old plan is preserved.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M03-03 - Structure tests: Calendar and cost reconciliation

Stories: #12-#16

**Steps:** Generate a full week, open the calendar and meal details, and inspect grocery rows. Manually total a sample meal ingredient cost and the displayed package basket.

**Expected:** The calendar has seven days and three required meal slots per day. Per-meal portions and weekly package cost are separately labeled; each matches its underlying ingredients/packages.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M03-04 - Format validity tests: Diet restrictions and literal requests

Stories: #12-#16

**Steps:** Select vegan plus nut allergy; generate. Repeat with No red meat and I only eat chicken. Inspect every ingredient and restriction readback; do not infer product-label allergen safety.

**Expected:** Catalog ingredient/name matching honors all recognized exclusions. Unsupported text is flagged for review. Ingredient overlap is consolidated; no unsafe plan is labeled fully checked.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.
