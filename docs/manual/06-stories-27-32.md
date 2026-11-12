# Manual acceptance tests - group 6: stories #27-#32

Execution type: Manual. These are authored test procedures, not automated test passes. A human has not executed this sheet.

Preconditions: a disposable local account/database, application running without an Anthropic key, browser developer tools available. Use developer fixtures only in a disposable environment. Record date, browser/version, commit and screenshots when executing.

## M06-01 - Boundary tests: Ratings and state transitions

Stories: #27-#32

**Steps:** Try ratings 0, 1, 5 and 6; mark a cooked/rated meal planned or skipped, and inspect later rating preferences.

**Expected:** Only 1-5 ratings on cooked meals save. Resetting/skipping clears the old rating so it no longer biases future plans. Closed inventory cannot be edited through status endpoints.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M06-02 - Size limit tests: Check-in notes and shopping handoff limits

Stories: #27-#32

**Steps:** Save 500-character check-in notes, undo check-in, then try 501. In an isolated fixture, attempt a shopping payload with 201 lines.

**Expected:** Long notes are rejected without closing/settling the plan; shopping payloads above 200 lines are rejected without sending to the provider.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M06-03 - Structure tests: Grocery persistence, weekly learning and inventory

Stories: #27-#32

**Steps:** Check/uncheck groceries and reload; force a network save failure and confirm rollback. Cook and rate meals, submit a check-in with leftovers and less cooking time, then generate next week. On a disposable account, exercise Send to Instacart both without a key and with a development key.

**Expected:** Check state persists; failed saves roll back. Settlement happens once, leftovers carry into pantry, and next-week choices reflect ratings/notes/time. Missing-key handoff is clear; with a valid key, unchecked items open an Instacart list for review, never an automatic order.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.

## M06-04 - Format validity tests: Check-in choices and provider response

Stories: #27-#32

**Steps:** Submit unknown overall/cook_time/variety values. With a developer transport fixture, return timeout, 401, malformed JSON or a non-Instacart shopping URL.

**Expected:** Invalid choices return 422 without changing inventory. Provider errors use safe messages, never leak API keys and never redirect to an untrusted host.

**Status:** Not run

**Actual result / tester / date / evidence:** Pending manual execution.
