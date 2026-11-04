"""Lay a plan out like a calendar week: events positioned on a time grid, with Google-Calendar-style lanes
for overlaps. Pure functions (no DB, no HTTP) so the layout is easy to test."""
import datetime as dt
from typing import Dict, List, Optional, Sequence

from app.services.schedule import PRE_WEEK, sessions_by_day
from app.services.types import WEEKDAYS
from app.services.timing import EAT, MIN_VISUAL, timed_sessions

HOUR_START, HOUR_END = 7, 21  # visible range of the grid
PX = 1.25  # pixels per minute on the grid
HOUR_PX = 60 * PX
GRID_PX = (HOUR_END - HOUR_START) * HOUR_PX


def fmt_time(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def week_start_for(created: dt.date) -> dt.date:
    """Monday of the plan's week; plans made on a weekend are for the coming week."""
    monday = created - dt.timedelta(days=created.weekday())
    return monday + dt.timedelta(days=7) if created.weekday() >= 5 else monday


def assign_lanes(events: List[dict]) -> None:
    """Side-by-side columns for overlapping events (sets 'lane' and 'lanes' on each)."""
    events.sort(key=lambda e: (e["start"], -e["visual"]))
    cluster: List[dict] = []
    lane_ends: List[int] = []
    cluster_end = -1
    for e in events:
        if cluster and e["start"] >= cluster_end:
            for c in cluster:
                c["lanes"] = len(lane_ends)
            cluster, lane_ends, cluster_end = [], [], -1
        for i, end in enumerate(lane_ends):
            if end <= e["start"]:
                e["lane"], lane_ends[i] = i, e["start"] + e["visual"]
                break
        else:
            e["lane"] = len(lane_ends)
            lane_ends.append(e["start"] + e["visual"])
        cluster.append(e)
        cluster_end = max(cluster_end, e["start"] + e["visual"])
    for c in cluster:
        c["lanes"] = len(lane_ends)


def _place(e: dict, hour_start: int = HOUR_START) -> dict:
    e["visual"] = max(e["dur"], MIN_VISUAL)
    e["top"] = round((e["start"] - hour_start * 60) * PX, 1)
    e["height"] = round(e["visual"] * PX, 1)
    e["time"] = fmt_time(e["start"])
    e.setdefault("lane", 0)
    e.setdefault("lanes", 1)
    return e


def build_columns(meals: Sequence[dict], sessions: Sequence[dict], days: Sequence[dict], start: dt.date,
                  today: Optional[dt.date] = None, hour_start: int = HOUR_START, cooking_windows=None, meal_times=None, external_slots=(), earliest_day=-1, earliest_minute=0) -> List[dict]:
    """meals: dicts with id/day/slot/name/cost/status/pinned/cook_day/frozen/cook_minutes.
    sessions: from schedule.build_sessions. days: plan.days (for skipped flags).
    Returns one column per visible day; the Sunday-before column only exists if something is cooked then."""
    today = today or dt.date.today()
    by_cook_day = sessions_by_day(timed_sessions(sessions,cooking_windows,meal_times,earliest_day,earliest_minute))
    skipped = {d["weekday"] for d in days if d.get("skipped")}
    cols: List[dict] = []
    for day in range(PRE_WEEK, 7):
        if day == PRE_WEEK and not by_cook_day.get(PRE_WEEK):
            continue
        date = start + dt.timedelta(days=day)
        events: List[dict] = []
        for m in meals:
            if m["day"] != day:
                continue
            t, dur = EAT[m["slot"]]
            t=(meal_times or {}).get(m["slot"],t)
            events.append(_place(dict(kind="meal", start=t, dur=dur, **m), hour_start))
        for external in external_slots:
            if external['day']==day and not external.get('past'):
                slot=external['slot'];t=(meal_times or {}).get(slot,EAT[slot][0])
                events.append(_place(dict(kind='external',start=t,dur=EAT[slot][1],name=external['source'],slot=slot),hour_start))
        ses = by_cook_day.get(day, [])
        for s in ses:
            events.append(_place(dict(kind="cook", start=s["start"], dur=s["minutes"], name=s["name"], servings=s["servings"],
                                     minutes=s["minutes"], eats=s["eats"]), hour_start))
        assign_lanes(events)
        events.sort(key=lambda e: (e["start"], e["kind"]))
        cols.append(dict(day=day, prep=day == PRE_WEEK, name="Sunday" if day == PRE_WEEK else WEEKDAYS[day],
                         short="Sun" if day == PRE_WEEK else WEEKDAYS[day][:3], date=date, daynum=date.day,
                         today=date == today, skipped=day in skipped, events=events))
    return cols


def hour_labels(hour_start: int = HOUR_START, cooking_windows=None, meal_times=None, external_slots=(), earliest_day=-1, earliest_minute=0) -> List[dict]:
    return [dict(label=fmt_time(h * 60).replace(":00 ", " "), top=round((h - hour_start) * HOUR_PX, 1)) for h in range(hour_start, HOUR_END)]


def week_title(start: dt.date) -> str:
    end = start + dt.timedelta(days=6)
    if start.month == end.month:
        return f"{start.strftime('%b')} {start.day} – {end.day}, {end.year}"
    return f"{start.strftime('%b')} {start.day} – {end.strftime('%b')} {end.day}, {end.year}"
