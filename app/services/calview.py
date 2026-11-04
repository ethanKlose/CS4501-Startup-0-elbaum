"""Lay a plan out like a calendar week: events positioned on a time grid, with Google-Calendar-style lanes
for overlaps. Pure functions (no DB, no HTTP) so the layout is easy to test."""
import datetime as dt
from typing import Dict, List, Optional, Sequence

from app.services.schedule import PRE_WEEK, sessions_by_day
from app.services.types import WEEKDAYS

HOUR_START, HOUR_END = 7, 21  # visible range of the grid
EAT = {"breakfast": (8 * 60, 60), "lunch": (12 * 60 + 30, 60), "dinner": (18 * 60 + 30, 75)}  # start minute, duration
PX = 1.25  # pixels per minute on the grid
HOUR_PX = 60 * PX
GRID_PX = (HOUR_END - HOUR_START) * HOUR_PX
PREP_START = 10 * 60  # Sunday-before cooking starts at 10:00
COOK_END = 18 * 60 + 15  # weekday cooking finishes by 6:15 PM, before dinner
MIN_VISUAL = 36  # shortest event height in minutes, so titles stay readable


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


def _place(e: dict) -> dict:
    e["visual"] = max(e["dur"], MIN_VISUAL)
    e["top"] = round((e["start"] - HOUR_START * 60) * PX, 1)
    e["height"] = round(e["visual"] * PX, 1)
    e["time"] = fmt_time(e["start"])
    e.setdefault("lane", 0)
    e.setdefault("lanes", 1)
    return e


def build_columns(meals: Sequence[dict], sessions: Sequence[dict], days: Sequence[dict], start: dt.date,
                  today: Optional[dt.date] = None) -> List[dict]:
    """meals: dicts with id/day/slot/name/cost/status/pinned/cook_day/frozen/cook_minutes.
    sessions: from schedule.build_sessions. days: plan.days (for skipped flags).
    Returns one column per visible day; the Sunday-before column only exists if something is cooked then."""
    today = today or dt.date.today()
    by_cook_day = sessions_by_day(sessions)
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
            events.append(_place(dict(kind="meal", start=t, dur=dur, **m)))
        ses = by_cook_day.get(day, [])
        if ses:
            # stack sessions back to back using their *visual* height so short ones never overlap
            total = sum(max(s["minutes"], MIN_VISUAL) for s in ses)
            cursor = PREP_START if day == PRE_WEEK else max(9 * 60, COOK_END - total)
            for s in ses:
                events.append(_place(dict(kind="cook", start=cursor, dur=s["minutes"], name=s["name"], servings=s["servings"],
                                         minutes=s["minutes"], eats=s["eats"])))
                cursor += max(s["minutes"], MIN_VISUAL)
        assign_lanes(events)
        events.sort(key=lambda e: (e["start"], e["kind"]))
        cols.append(dict(day=day, prep=day == PRE_WEEK, name="Sunday" if day == PRE_WEEK else WEEKDAYS[day],
                         short="Sun" if day == PRE_WEEK else WEEKDAYS[day][:3], date=date, daynum=date.day,
                         today=date == today, skipped=day in skipped, events=events))
    return cols


def hour_labels() -> List[dict]:
    return [dict(label=fmt_time(h * 60).replace(":00 ", " "), top=round((h - HOUR_START) * HOUR_PX, 1)) for h in range(HOUR_START, HOUR_END)]


def week_title(start: dt.date) -> str:
    end = start + dt.timedelta(days=6)
    if start.month == end.month:
        return f"{start.strftime('%b')} {start.day} – {end.day}, {end.year}"
    return f"{start.strftime('%b')} {start.day} – {end.strftime('%b')} {end.day}, {end.year}"
