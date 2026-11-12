# Generate directly from Preferences

Preferences now offers **Save & generate plan**, alongside **Save only**. The
primary action submits all sections, validates and saves them, then generates a
new current plan for the same week. Compatible pins keep their existing behavior;
previous plans remain in history. A failed generation keeps the previous plan
and inventory intact while retaining the successfully saved preferences. Invalid
preferences are shown inline without generating or partially saving them.

Generation runs in the thread pool and shows the existing progress overlay.
Duplicate submits are blocked. A one-use saved marker clears the previous form
draft when returning to Preferences. First-time setup also generates once,
without triggering the older onboarding auto-submit a second time.

Verification: the survey/nutrition integration and survey validation checks passed
(64 cases before adding the first-time case), followed by all 6 final feature
integration cases and all 44 DOM cases. Tests used the offline engine/controlled
failures and made no paid AI calls. The full Python suite was not rerun for this
small follow-up. No environment or database schema changes are needed.
