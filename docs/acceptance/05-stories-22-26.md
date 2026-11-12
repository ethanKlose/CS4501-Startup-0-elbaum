# Acceptance group 5: user stories #22-#26

This commit covers 5 story records. Existing working behavior is retained; fixes and regressions focus on observed gaps. Automated evidence is separate from pending human manual execution.

| Story | Acceptance evidence | Manual cases |
| --- | --- | --- |
| [#22 [Day controls] Re-verify regenerated plans](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/22) | whole-week re-verification; test_reverify.py/test_story_grocery_acceptance.py | M05-01 through M05-04 |
| [#23 [Day controls] Swap a single meal](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/23) | single-slot swap isolation; test_day_controls.py/e2e/smoke.cjs | M05-01 through M05-04 |
| [#24 [Grocery] Generate grocery list from plan](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/24) | case/unit-normalized merged groceries; test_story_grocery_acceptance.py/test_grocery.py | M05-01 through M05-04 |
| [#25 [Grocery] Exclude pantry items from list](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/25) | full and partial pantry deductions; test_inventory.py/test_grocery.py | M05-01 through M05-04 |
| [#26 [Grocery] Group list by store section](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/26) | each item in one store section; test_story_grocery_acceptance.py/test_grocery.py | M05-01 through M05-04 |

Manual procedures: [group 5](../manual/05-stories-22-26.md). Full automated execution results are in [STORY_COMPLETION.md](../../STORY_COMPLETION.md). Tests are located under tests/.
