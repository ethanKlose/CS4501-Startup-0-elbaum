# Acceptance group 6: user stories #27-#32

This commit covers 6 story records. Existing working behavior is retained; fixes and regressions focus on observed gaps. Automated evidence is separate from pending human manual execution.

| Story | Acceptance evidence | Manual cases |
| --- | --- | --- |
| [#27 [Grocery] Check off items while shopping](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/27) | persisted check-offs and failed-save rollback; test_grocery.py/e2e/smoke.cjs | M06-01 through M06-04 |
| [#28 [Grocery] Send list to Instacart](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/28) | Instacart shopping-list handoff; test_story_checkin_handoff.py; LIVE KEY REQUIRED | M06-01 through M06-04 |
| [#29 [Check-in] Mark meals cooked or skipped](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/29) | meal states and rating reset; test_story_checkin_handoff.py/test_checkin.py | M06-01 through M06-04 |
| [#30 [Check-in] Rate cooked meals](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/30) | ratings feed future preferences; test_checkin.py | M06-01 through M06-04 |
| [#31 [Check-in] Weekly check-in](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/31) | validated check-in, no silent truncation; test_story_checkin_handoff.py/test_checkin.py | M06-01 through M06-04 |
| [#32 [Check-in] Carry leftover pantry items into next week](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/32) | idempotent inventory carry-over/undo; test_inventory.py/test_inventory_concurrency.py/test_history_undo.py | M06-01 through M06-04 |

Manual procedures: [group 6](../manual/06-stories-27-32.md). Full automated execution results are in [STORY_COMPLETION.md](../../STORY_COMPLETION.md). Tests are located under tests/.
