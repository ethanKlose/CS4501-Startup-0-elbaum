# Acceptance group 2: user stories #7-#11

This commit covers 5 story records. Existing working behavior is retained; fixes and regressions focus on observed gaps. Automated evidence is separate from pending human manual execution.

| Story | Acceptance evidence | Manual cases |
| --- | --- | --- |
| [#7 [Survey] List pantry items](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/7) | bounded pantry input/deductions; test_story_plan_limits.py/test_inventory.py | M02-01 through M02-04 |
| [#8 [Survey] Short initial survey](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/8) | optional wizard steps; test_survey.py/e2e/smoke.cjs; human 3-minute timing pending | M02-01 through M02-04 |
| [#9 [Survey] Edit survey answers later](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/9) | saved-answer editing; test_survey.py | M02-01 through M02-04 |
| [#10 [Plan] Generate a full week of meals](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/10) | bounded plan schema and 21-slot coverage; test_plan.py/test_story_plan_limits.py | M02-01 through M02-04 |
| [#11 [Plan] Verify plan against budget before display](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/11) | whole-package and pantry-aware budget validation; test_budget_feasibility.py/test_pricing.py | M02-01 through M02-04 |

Manual procedures: [group 2](../manual/02-stories-7-11.md). Full automated execution results are in [STORY_COMPLETION.md](../../STORY_COMPLETION.md). Tests are located under tests/.
