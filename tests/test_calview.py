import datetime as dt

from app.services.calview import (EAT, HOUR_PX, HOUR_START, PX, assign_lanes, build_columns, fmt_time, hour_labels, week_start_for,
                                  week_title)
from app.services.schedule import build_sessions


def meal(id, day, slot, cook_day=None, minutes=20, name=None):
    return dict(id=id, day=day, slot=slot, name=name or f"Meal {id}", cost=2.0, status="planned", pinned=False,
                cook_day=day if cook_day is None else cook_day, frozen=False, cook_minutes=minutes, ingredients=[])


def test_time_formatting_and_week_math():
    assert fmt_time(0) == "12:00 AM" and fmt_time(8 * 60) == "8:00 AM" and fmt_time(12 * 60 + 30) == "12:30 PM" and fmt_time(18 * 60 + 5) == "6:05 PM"
    assert week_start_for(dt.date(2026, 11, 4)) == dt.date(2026, 11, 2)  # Wednesday -> that Monday
    assert week_start_for(dt.date(2026, 11, 7)) == dt.date(2026, 11, 9)  # Saturday -> next Monday
    assert week_title(dt.date(2026, 11, 2)) == "Nov 2 – 8, 2026" and week_title(dt.date(2026, 10, 26)) == "Oct 26 – Nov 1, 2026"
    assert hour_labels()[0] == dict(label="7 AM", top=0) and hour_labels()[-1]["label"] == "8 PM" and hour_labels()[1]["top"] == HOUR_PX


def test_meals_land_at_their_eating_times():
    ms = [meal(1, 0, "breakfast", minutes=0), meal(2, 0, "dinner", minutes=0)]
    cols = build_columns(ms, [], [], dt.date(2026, 11, 2))
    assert [c["day"] for c in cols] == list(range(7))  # no Sunday-before column when nothing is cooked then
    ev = {e["slot"]: e for e in cols[0]["events"]}
    assert ev["breakfast"]["top"] == (EAT["breakfast"][0] - HOUR_START * 60) * PX and ev["breakfast"]["time"] == "8:00 AM"
    assert ev["dinner"]["dur"] == 75 and ev["dinner"]["height"] == round(75 * PX, 1)


def test_sunday_before_column_appears_for_prep_sessions():
    ms = [meal(1, 2, "dinner", cook_day=-1, name="Chili"), meal(2, 3, "dinner", cook_day=-1, name="Chili")]
    sessions = build_sessions(ms)
    cols = build_columns(ms, sessions, [], dt.date(2026, 11, 2))
    assert cols[0]["prep"] and cols[0]["date"] == dt.date(2026, 11, 1) and cols[0]["short"] == "Sun"
    cook = [e for e in cols[0]["events"] if e["kind"] == "cook"]
    assert len(cook) == 1 and cook[0]["servings"] == 2 and cook[0]["start"] == 10 * 60


def test_weekday_cooking_ends_before_dinner_and_sessions_do_not_overlap():
    ms = [meal(1, 1, "dinner", cook_day=1, name="A", minutes=30), meal(2, 1, "lunch", cook_day=1, name="B", minutes=20)]
    cols = build_columns(ms, build_sessions(ms), [], dt.date(2026, 11, 2))
    day1 = next(c for c in cols if c["day"] == 1)
    cooks = sorted((e for e in day1["events"] if e["kind"] == "cook"), key=lambda e: e["start"])
    assert cooks[-1]["start"] + cooks[-1]["dur"] <= 18 * 60 + 15
    assert cooks[0]["start"] + cooks[0]["dur"] <= cooks[1]["start"]


def test_overlaps_get_side_by_side_lanes_and_non_overlaps_do_not():
    evs = [dict(start=600, visual=60, dur=60), dict(start=620, visual=60, dur=60), dict(start=900, visual=45, dur=45)]
    assign_lanes(evs)
    a, b, c = sorted(evs, key=lambda e: e["start"])
    assert (a["lane"], b["lane"], a["lanes"], b["lanes"]) == (0, 1, 2, 2)
    assert (c["lane"], c["lanes"]) == (0, 1)


def test_lane_invariant_on_dense_days():
    import random

    rng = random.Random(1)
    for _ in range(50):
        evs = [dict(start=rng.randint(420, 1200), visual=rng.choice([30, 45, 60, 90]), dur=30) for _ in range(rng.randint(1, 8))]
        assign_lanes(evs)
        for x in evs:
            assert 0 <= x["lane"] < x["lanes"]
            for y in evs:
                if x is not y and x["lane"] == y["lane"]:
                    assert x["start"] + x["visual"] <= y["start"] or y["start"] + y["visual"] <= x["start"]


def test_today_and_skipped_flags():
    ms = [meal(1, 2, "lunch", minutes=0)]
    cols = build_columns(ms, [], [dict(weekday=4, skipped=True)], dt.date(2026, 11, 2), today=dt.date(2026, 11, 4))
    assert [c["day"] for c in cols if c["today"]] == [2] and [c["day"] for c in cols if c["skipped"]] == [4]


def test_short_back_to_back_cook_sessions_never_overlap():
    ms = [meal(1, 1, "lunch", cook_day=1, name="A", minutes=10), meal(2, 1, "dinner", cook_day=1, name="B", minutes=12)]
    day1 = next(c for c in build_columns(ms, build_sessions(ms), [], dt.date(2026, 11, 2)) if c["day"] == 1)
    cooks = sorted((e for e in day1["events"] if e["kind"] == "cook"), key=lambda e: e["start"])
    assert len(cooks) == 2 and cooks[0]["start"] + cooks[0]["visual"] <= cooks[1]["start"]
    assert all(e["lanes"] == 1 for e in cooks)


def test_cooking_finishes_before_breakfast_and_lunch():
    ms = [meal(1, 0, 'breakfast', name='Oatmeal', minutes=8),
          meal(2, 0, 'lunch', name='Rice bowl', minutes=25),
          meal(3, 0, 'dinner', name='Soup', minutes=30)]
    cols = build_columns(ms, build_sessions(ms), [], dt.date(2026, 11, 9))
    cooks = [e for e in cols[0]['events'] if e['kind'] == 'cook']
    for event in cooks:
        supplied = [m for m in ms if m['name'] == event['name']]
        assert event['start'] >= 0
        assert event['start'] + event['dur'] <= min(EAT[m['slot']][0] for m in supplied)


def test_long_breakfast_prep_is_visible_on_an_expanded_grid():
    ms = [meal(1, 0, 'breakfast', name='Slow breakfast', minutes=120)]
    cols = build_columns(ms, build_sessions(ms), [], dt.date(2026, 11, 9), hour_start=6)
    cook = next(e for e in cols[0]['events'] if e['kind'] == 'cook')
    assert cook['time'] == '6:00 AM' and cook['top'] == 0
