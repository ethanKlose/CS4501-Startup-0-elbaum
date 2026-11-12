# Kroger manual acceptance procedures

All procedures below are **NOT RUN BY A HUMAN** in this delivery. Record the date,
actual account, store, observations, result and any blocker when you execute them.
Never paste client secrets, OAuth codes, tokens or password screenshots into logs.

| ID / category | Procedure | Expected result |
| --- | --- | --- |
| K-M01 / structure | Register a real Public API app; connect a shopper account; restart PlateJoy | Correct local user remains connected with encrypted server-side credentials; Google still connects/syncs |
| K-M02 / boundary | Find a store with a valid ZIP; try a malformed ZIP and a ZIP with no returned store | Real stores and addresses appear; invalid/no-store cases are explicit; no invented location |
| K-M03 / structure | Check off one grocery and cover another with pantry stock; start a review | Only remaining shortfalls appear; displayed recipe amounts retain their original units |
| K-M04 / format validity | Search a real product; compare its name, UPC, package size, available price and label link with Kroger | Fields are readable, UPC leading zeroes preserved, unavailable prices are not shown as zero |
| K-M05 / boundary | Select one product with one package, then change its count before using an old confirmation tab | Old confirmation fails; the new review shows the changed count and any omitted ingredients |
| K-M06 / size limit | Try 0, 100, fractional and nonnumeric package counts; use automated tests for 50-product/100-row caps | Invalid counts are rejected before cart submission; real cart quantity matches explicitly reviewed package count |
| K-M07 / user flow | Confirm a deliberately small test transfer, then open Kroger and choose the matching store/fulfillment | API acknowledgement is shown; inspect actual cart items and counts; no order/payment; remove test products manually |
| K-M08 / reliability | Double-click the same confirmation, then repeat it after restarting PlateJoy | A single API submission for that review; no second automatic addition |
| K-M09 / error recovery | Interrupt a real transfer only if you are comfortable checking/cleaning the cart afterward | Unknown result blocks retry until you inspect Kroger and explicitly acknowledge; no automatic resend |
| K-M10 / account safety | Use another PlateJoy login to submit the first user's review; disconnect Kroger separately | Foreign review cannot transfer; local Kroger credentials are removed; Google credentials and grocery ledger remain |

Real provider registration, OAuth and cart behavior remain **BLOCKED / UNVERIFIED**
until an account owner executes these checks. Automated controlled-provider tests
are separate evidence and must not be reported as manual or live acceptance.
