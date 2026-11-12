# Acceptance group 4: user stories #17-#21

This commit covers 5 story records. Existing working behavior is retained; fixes and regressions focus on observed gaps. Automated evidence is separate from pending human manual execution.

| Story | Acceptance evidence | Manual cases |
| --- | --- | --- |
| [#17 [Calendar] Schedule prep blocks on less busy days](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/17) | bounded/strict cooking windows and deadlines; test_windows.py/test_late_cooking.py | M04-01 through M04-04 |
| [#18 [Calendar] Open a meal to see recipe details](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/18) | recipe detail and dialog; test_calendar.py/e2e/smoke.cjs | M04-01 through M04-04 |
| [#19 [Day controls] Mark a day as changed](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/19) | skip/restore and inventory updates; test_day_controls.py | M04-01 through M04-04 |
| [#20 [Day controls] Pin meals to keep on regenerate](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/20) | exact pins and closed-history protection; test_reverify.py/test_story_calendar_controls.py | M04-01 through M04-04 |
| [#21 [Day controls] Regenerate week with one click](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/21) | regeneration with saved answers; test_reverify.py/test_day_controls.py | M04-01 through M04-04 |

Manual procedures: [group 4](../manual/04-stories-17-21.md). Full automated execution results are in [STORY_COMPLETION.md](../../STORY_COMPLETION.md). Tests are located under tests/.
