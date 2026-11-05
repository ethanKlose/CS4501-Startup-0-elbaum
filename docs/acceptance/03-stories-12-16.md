# Acceptance group 3: user stories #12-#16

This commit covers 5 story records. Existing working behavior is retained; fixes and regressions focus on observed gaps. Automated evidence is separate from pending human manual execution.

| Story | Acceptance evidence | Manual cases |
| --- | --- | --- |
| [#12 [Plan] Verify plan against restrictions and free-text requests](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/12) | diet validator/readback; test_diet_regressions.py/test_preference_safety.py | M03-01 through M03-04 |
| [#13 [Plan] Share ingredients across meals](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/13) | ingredient reuse scoring and normalized sharing statistics; test_plan.py/test_grocery.py | M03-01 through M03-04 |
| [#14 [Plan] Show cost per meal and weekly total](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/14) | portion versus package estimates; test_pricing.py/test_story_verification_acceptance.py | M03-01 through M03-04 |
| [#15 [Plan] Clear message when constraints can't be met](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/15) | required-slot conflict explanations; test_conflicts.py/test_story_verification_acceptance.py | M03-01 through M03-04 |
| [#16 [Calendar] Weekly calendar view of meals](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/16) | weekly responsive calendar; test_calendar.py/e2e/audit-regressions.cjs | M03-01 through M03-04 |

Manual procedures: [group 3](../manual/03-stories-12-16.md). Full automated execution results are in [STORY_COMPLETION.md](../../STORY_COMPLETION.md). Tests are located under tests/.
