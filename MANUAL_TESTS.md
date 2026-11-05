# Manual test register

The four requested categories are **Boundary tests**, **Size limit tests**, **Structure tests**, and **Format validity tests**. There are 24 manual cases, six per category, covering all 31 user stories in six groups.

- [Group 1: stories #2-#6](docs/manual/01-stories-2-6.md)
- [Group 2: stories #7-#11](docs/manual/02-stories-7-11.md)
- [Group 3: stories #12-#16](docs/manual/03-stories-12-16.md)
- [Group 4: stories #17-#21](docs/manual/04-stories-17-21.md)
- [Group 5: stories #22-#26](docs/manual/05-stories-22-26.md)
- [Group 6: stories #27-#32](docs/manual/06-stories-27-32.md)

Editable execution logs: [CSV](docs/manual/MANUAL_TEST_LOG.csv) and [JSON](docs/manual/MANUAL_TEST_LOG.json).

All manual records start **Not run**. They have not been performed by a human, and no manual pass rate is claimed. Automated Python/browser checks exercise many of the same risks and are recorded separately in STORY_COMPLETION.md. They are not counted as executed manual tests. Update a manual record only after carrying out its steps, with actual observations, tester, date, commit and evidence. Preserve failed/blocked attempts. A live Instacart test requires a development key; three-minute onboarding requires a timed human attempt.

Boundary cases probe thresholds and state transitions. Size cases probe maximum lengths/counts. Structure cases probe complete workflows and data relationships. Format cases probe syntax, type, choices and provider response shape. These labels describe test techniques, not five separate methods; the request listed four categories.
