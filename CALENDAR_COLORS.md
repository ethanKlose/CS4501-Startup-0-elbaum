# Organized Google Calendar colors

This incremental patch applies after the Beta integrations/OpenAI live-test patch
already installed in your checkout. It does not contain or change your .env.

| Event | Google color | Meaning |
| --- | --- | --- |
| Breakfast | Yellow / Banana (5) | Morning meals |
| Lunch | Green / Basil (10) | Midday meals |
| Dinner | Blue / Blueberry (9) | Evening meals |
| Cooking and prep | Purple / Grape (3) | Preparation rather than eating |
| Eating out / dining hall | Gray / Graphite (8) | Meals outside the home plan |

The Connected apps page shows the same labeled legend. Categories come from the
saved meal slot or event type; recipe titles are not used to guess a category.
Google's own palette controls the event fill/text rendering.

## Apply in Windows Git Bash

Stop the server with Ctrl+C, then run:

```bash
cd "/c/Users/Kunaal Sastry/OneDrive/Desktop/KS_LLM"
git apply --check "$HOME/Downloads/KS_Calendar_Colors.patch"
git apply "$HOME/Downloads/KS_Calendar_Colors.patch"
.venv/Scripts/python.exe -m pytest tests/integration/test_google_calendar_colors.py -q
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

If the apply check fails, stop and inspect its output before applying. No new
packages or environment settings are needed.

Open http://127.0.0.1:8000/integrations and click **Sync current week**. Existing
PlateJoy events are recolored in place; their IDs, recipe names and times do not
change. No meal regeneration, Google reconnection or OpenAI call is needed.
Sync again and the correctly colored events should be reported as unchanged.
A manually changed Google event color is restored to its category on resync,
consistent with the existing one-way sync behavior.

The sync targets only the current plan's week. To recolor a different week, it
must be the current plan supported by the existing sync action. Calendar-file
imports do not inherit these API color IDs automatically.

## Verification

54 focused regression tests passed in 6.09 seconds on Linux / Python 3.12.14,
including 8 new tests: five category cases, legacy-event recoloring without
new events, a color-only change, and the page legend. No external API calls were
made. Existing Google workflows, skipped/restored events, DST conversions and ICS
exports also passed. The full project suite was not rerun for this small change;
the preceding Beta update's 653-test result is historical evidence for its base.

Manual follow-up (not executed here): resync your already connected Google account,
check all five categories that are present, and verify a second sync adds no copies.

Official Google palette:
https://developers.google.com/apps-script/reference/calendar/event-color
API event color field:
https://developers.google.com/workspace/calendar/api/v3/reference/events
