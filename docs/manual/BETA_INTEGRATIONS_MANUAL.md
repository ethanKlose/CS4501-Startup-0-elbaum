# Beta integration manual acceptance procedures

Status for every procedure below: **NOT RUN BY A HUMAN**. Automated coverage is
separate. Record your actual account, date, browser, observations and pass/fail
when you execute them. Do not infer manual passes from automated tests.

| ID / category | Procedure | Expected result |
| --- | --- | --- |
| BETA-M01 / user flow | Connect a Google test account; sync a normal 21-meal week; open Google Calendar | Correct dates, meals and scheduled prep blocks appear in the connected account's primary calendar |
| BETA-M02 / boundary | Sync the same week twice; regenerate in the app and sync again | Repeated sync has no duplicate events; regenerated recipes update the same week; personal events remain |
| BETA-M03 / boundary | Skip a meal, sync, restore it, sync again | Its meal event and unneeded prep disappear, then return appropriately; shared batch servings remain accurate |
| BETA-M04 / structure | Add an outside meal and prep before Monday; compare app, ICS import and Google | Dates, recipe instructions, outside-meal labels and pre-week prep agree |
| BETA-M05 / format validity | Use a week spanning a daylight-saving transition and a recipe with punctuation/newlines | Correct local times and readable text; no corrupt ICS lines or literal escape sequences in Google titles |
| BETA-M06 / error recovery | Interrupt network during sync, restore network and retry; deny consent separately | Partial work is reported; retry finishes without duplicates; consent denial does not alter the plan |
| BETA-M07 / size limit | Review a supported large grocery list and verify the 200-item boundary with the automated payload test | Up to 200 valid items serialize; over-limit payload is rejected; no order is placed |
| BETA-M08 / format validity | Review a grocery item using a supported unit and one using a scoop/can-like unsupported unit | Numeric quantity matches the list; unsupported unit remains visible with a warning to review product sizes |
| BETA-M09 / user flow | Mark one grocery item bought, review the remaining list, send to Instacart and choose a store | Bought/pantry items are absent; unchecked names/quantities transfer; user reviews matches and prices before purchase |
| BETA-M10 / account safety | Log in as another local user, attempt the first user's plan ID; disconnect Google and retry sync | Foreign/stale form fails; local credentials are cleared on disconnect; no personal calendar event is removed |

Capture evidence locally without keys or tokens. If a provider account cannot be
configured or the page cannot be opened, record **BLOCKED**, not PASS.
