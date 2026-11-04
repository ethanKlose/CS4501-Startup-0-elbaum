# Student usability study

This repository contains collection tools and a study procedure, not completed human-subject results. Do not claim that the app saves time or money based only on automated tests.

1. Invite a small group of willing students and explain what will be recorded. Participation and anonymous numeric export are optional.
2. Ask each student to record their usual planning time and an ordinary grocery receipt as a baseline.
3. Have them register, describe their real kitchen, set their schedule, add pantry stock, generate a plan, inspect a recipe, replace one meal and use the grocery list. Observe without coaching first.
4. Ask them to follow the plan for a week and mark meals actually cooked/skipped. Record checkout spending separately from estimated portions.
5. Have them submit `/feedback`: actual spending, planning time, baseline planning time, ease and skipped/confusing items. The form captures planned/cooked meal counts and the package estimate.
6. Review failures, recipe changes and differences between estimated and actual spending. Report sample size, missing reports and self-report limitations. Compare each student's app time against their own baseline rather than asserting causation.
7. For participants who opt in, the repository owner can run `python -m scripts.export_study > study-results.json` in the configured virtual environment. The export excludes emails, notes, plan IDs and exact timestamps. Production participant identifiers are HMAC pseudonyms; local exports use fresh random identifiers per export; keep the signing secret private. Do not publish server databases.

No students have been recruited or contacted by this implementation. No results have been fabricated. Obtain any course/institutional approvals required for your particular study before collecting data for research.
