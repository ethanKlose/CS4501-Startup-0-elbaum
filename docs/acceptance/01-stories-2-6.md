# Acceptance group 1: user stories #2-#6

This commit covers 5 story records. Existing working behavior is retained; fixes and regressions focus on observed gaps. Automated evidence is separate from pending human manual execution.

| Story | Acceptance evidence | Manual cases |
| --- | --- | --- |
| [#2 [Survey] Enter weekly grocery budget](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/2) | survey budget validation; test_survey.py | M01-01 through M01-04 |
| [#3 [Survey] Mark busy days and cooking time per day](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/3) | parse_minutes/day settings; test_story_survey_acceptance.py | M01-01 through M01-04 |
| [#4 [Survey] Select dietary restrictions and allergies](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/4) | restriction enum validation; test_story_survey_acceptance.py | M01-01 through M01-04 |
| [#5 [Survey] Set nutrition or fitness goal](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/5) | goal input/readback and validation; test_survey.py/test_generation_matrix.py | M01-01 through M01-04 |
| [#6 [Survey] Free-text preferences](https://github.com/ethanKlose/CS4501-Startup-0-elbaum/issues/6) | preference_text/diet parsing; test_preference_safety.py/test_story_survey_acceptance.py | M01-01 through M01-04 |

Manual procedures: [group 1](../manual/01-stories-2-6.md). Full automated execution results are in [STORY_COMPLETION.md](../../STORY_COMPLETION.md). Tests are located under tests/.
