"""Decide WHEN each dish gets cooked, separately from WHEN it is eaten.

The LLM chooses the meals; this deterministic module assigns each meal a cook day so that:
  * cooking minutes on a day never exceed that day's capacity (else the day is reported as overbooked),
  * food is eaten within its storage window (fridge, or freezer where it freezes well),
  * the same dish eaten several times is cooked in one batch (cheaper in time: see BATCH_FACTOR),
  * cooking is clustered on as few days as the user's prep style asks for.

Cook day -1 means "the Sunday before the week starts" (classic meal-prep day).
Reheating is free and is never counted as cooking time.
"""
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence, Tuple

from app.services.diet import term_hits
from app.services.types import SLOTS, WEEKDAYS, DayCtx
from app.services.timing import deadline_errors

PRE_WEEK = -1
BATCH_FACTOR = 0.4  # each extra serving of the same dish costs 40% of the base cook time
FREEZER_DAYS = 30
MAX_BATCH = 4  # servings of one dish cooked in one go; more than that is unrealistic and hogs a whole day
FRESH_WORDS = ("salad", "sandwich", "wrap", "toast", "smoothie", "parfait", "scramble", "quesadilla")
PREP_STYLES = {
    "auto": "Let the app decide",
    "daily": "Cook fresh most days",
    "sessions": "A couple of cooking sessions a week",
    "one_session": "One big session",
}


def day_label(day: int) -> str:
    return "Sunday (before the week)" if day == PRE_WEEK else WEEKDAYS[day]


# ----------------------------------------------------------------------------- storage safety


def _meal_text(meal: dict) -> str:
    return " ".join([meal.get("name", "")] + [i.get("name", "") for i in meal.get("ingredients", [])])


def is_fresh(meal: dict) -> bool:
    name = meal.get("name", "").lower()
    return any(w in name for w in FRESH_WORDS)


def storage_days(meal: dict) -> int:
    """Fridge life in days after cooking. 0 = nothing to cook (assembled on the spot).

    Deliberately conservative and derived from ingredients, never from what the LLM claims.
    """
    if meal.get("cook_minutes", 0) <= 0:
        return 0
    if is_fresh(meal):
        return 1
    text = _meal_text(meal)
    if term_hits(text, "seafood"):
        return 2
    if term_hits(text, "egg"):
        return 3
    if term_hits(text, "meat"):
        return 4
    return 5


def freezable(meal: dict) -> bool:
    return meal.get("cook_minutes", 0) > 0 and not is_fresh(meal)


# ----------------------------------------------------------------------------- capacity


def capacities(days: Sequence[DayCtx], style: str = "auto", prep_days: Iterable[int] = (), prep_minutes: int = 120) -> Dict[int, int]:
    """Cooking minutes available on each cook day, -1 (Sunday before the week) through 6."""
    caps = {d.weekday: (0 if d.skipped else d.minutes) for d in days}
    caps[PRE_WEEK] = next((d.minutes for d in days if d.weekday == 6), 0)
    for p in prep_days:  # preferred cook days get a longer window ("I can prep for 2 hours on Sunday")
        if p in caps and not next((d.skipped for d in days if d.weekday == p), False):
            caps[p] = max(caps[p], prep_minutes)
        if p == 6:
            caps[PRE_WEEK] = max(caps[PRE_WEEK], prep_minutes)
    if style == "daily":
        caps[PRE_WEEK] = 0
    return caps


# ----------------------------------------------------------------------------- scheduling


@dataclass
class Schedule:
    assign: Dict[Tuple[int, str], Tuple[int, bool]] = field(default_factory=dict)  # (day, slot) -> (cook_day, frozen)
    sessions: List[dict] = field(default_factory=list)
    used: Dict[int, int] = field(default_factory=dict)  # minutes booked per cook day
    caps: Dict[int, int] = field(default_factory=dict)

    @property
    def overbooked(self) -> Dict[int, Tuple[int, int]]:
        return {c: (u, self.caps.get(c, 0)) for c, u in self.used.items() if u > self.caps.get(c, 0)}


def batch_minutes(base: int, servings: int) -> int:
    return int(round(base * (1 + BATCH_FACTOR * (servings - 1))))


def _slot_idx(m: dict) -> Tuple[int, int]:
    return (m["day"], SLOTS.index(m["slot"]))


def schedule(meals: Sequence[dict], caps: Dict[int, int], style: str = "auto", prep_days: Iterable[int] = (),
             busy: Iterable[int] = ()) -> Schedule:
    """Try a few deterministic strategies and keep the one with the least overbooking, then the fewest cook days."""
    prep_days, busy = list(prep_days), list(busy)
    best = None
    for order in ("tight", "early"):
        for consolidate in (100.0, 20.0):
            cand = _build(meals, caps, style, prep_days, busy, order, consolidate)
            over = sum(u - cand.caps.get(c, 0) for c, u in cand.used.items() if u > cand.caps.get(c, 0))
            key = (len(deadline_errors(cand.sessions)), over, len(cand.used))
            if best is None or key < best[0]:
                best = (key, cand)
    return best[1]


def _build(meals: Sequence[dict], caps: Dict[int, int], style: str, prep_days: Iterable[int], busy: Iterable[int],
           order: str, consolidate: float) -> Schedule:
    prefs = set(prep_days) | ({PRE_WEEK} if 6 in set(prep_days) else set())
    busy = set(busy)
    remaining = dict(caps)
    for c in range(PRE_WEEK, 7):
        remaining.setdefault(c, 0)
    out = Schedule(caps=dict(remaining))
    used_days: set = set()

    dishes: Dict[str, List[dict]] = {}
    for m in meals:
        if m["cook_minutes"] <= 0:
            out.assign[(m["day"], m["slot"])] = (m["day"], False)  # nothing to cook
        else:
            dishes.setdefault(m["name"], []).append(m)

    def tightness(name):
        ms = dishes[name]
        if order == "early":  # most constrained first: dishes eaten earliest have the fewest possible cook days
            return (min(_slot_idx(m) for m in ms), -sum(m["cook_minutes"] for m in ms), name)
        return (storage_days(ms[0]), -sum(m["cook_minutes"] for m in ms), name)

    for name in sorted(dishes, key=tightness):
        members = sorted(dishes[name], key=_slot_idx)
        rep = members[0]
        base = max(m["cook_minutes"] for m in members)
        fridge, can_freeze = storage_days(rep), freezable(rep)
        reach = FREEZER_DAYS if (can_freeze and style != "daily") else fridge
        if style == "daily":
            reach = 0
        pending = list(members)

        while pending:
            e0 = pending[0]
            options = []
            for c in range(max(PRE_WEEK, e0["day"] - reach), e0["day"] + 1):
                batch = [m for m in pending if 0 <= m["day"] - c <= reach][:MAX_BATCH]
                while batch and batch_minutes(base, len(batch)) > remaining[c]:
                    batch.pop()  # shrink the batch until it fits that day
                if not batch or batch[0] is not e0:
                    continue
                need = batch_minutes(base, len(batch))
                n_frozen = sum(1 for m in batch if m["day"] - c > fridge)
                score = 0.0
                if c in used_days:
                    score += consolidate
                elif used_days:
                    score -= {"one_session": 300, "sessions": 40 if len(used_days) >= 3 else 10}.get(
                        style, 30 if len(used_days) >= 2 else 12)
                score += 25 if c in prefs else 0
                score += 15 if (style == "one_session" and c == PRE_WEEK) else 0
                score -= 20 if c in busy else 0
                score -= 2 * (e0["day"] - c) + n_frozen
                score += 3.0 * (remaining[c] - need) / max(out.caps.get(c, 1), 1)
                score += 2 * len(batch)  # bigger batches are better
                options.append((score, c, batch, need))
            if options:
                _, c, batch, need = max(options, key=lambda o: (o[0], o[1]))
            else:  # nothing fits anywhere: book the roomiest legal day anyway and let the caller report it
                legal = [c for c in range(max(PRE_WEEK, e0["day"] - reach), e0["day"] + 1)] or [e0["day"]]
                c = max(legal, key=lambda x: (remaining[x], x))
                batch = [m for m in pending if 0 <= m["day"] - c <= reach][:MAX_BATCH] or [e0]
                if batch[0] is not e0:
                    batch = [e0]
                need = batch_minutes(base, len(batch))
            for m in batch:
                out.assign[(m["day"], m["slot"])] = (c, (m["day"] - c) > fridge)
            remaining[c] -= need
            out.used[c] = out.used.get(c, 0) + need
            used_days.add(c)
            ids = {id(m) for m in batch}
            pending = [m for m in pending if id(m) not in ids]

    out.sessions = build_sessions([dict(m, cook_day=out.assign[(m["day"], m["slot"])][0],
                                        frozen=out.assign[(m["day"], m["slot"])][1]) for m in meals])
    return out


def build_sessions(meals: Iterable[dict]) -> List[dict]:
    """One session per real batch. `meals` need day, slot, name, cook_minutes, cook_day, frozen (saved or fresh)."""
    groups: Dict[Tuple[int, str], List[dict]] = {}
    for m in meals:
        if m["cook_minutes"] > 0:
            groups.setdefault((m["cook_day"], m["name"]), []).append(m)
    sessions = []
    for (c, name), ms in sorted(groups.items()):
        ms.sort(key=_slot_idx)
        base = max(m["cook_minutes"] for m in ms)
        for i in range(0, len(ms), MAX_BATCH):
            chunk = ms[i:i + MAX_BATCH]
            sessions.append(dict(cook_day=c, name=name, servings=len(chunk), minutes=batch_minutes(base, len(chunk)),
                                 eats=[dict(day=m["day"], slot=m["slot"], frozen=m["frozen"]) for m in chunk]))
    return sessions


def overbook_messages(sched: Schedule) -> List[str]:
    return [f"{day_label(c)} needs {used} cooking minutes but only {cap} are available. "
            f"Add time that day or use a longer prep session."
            for c, (used, cap) in sorted(sched.overbooked.items())]


def sessions_by_day(sessions: Sequence[dict]) -> Dict[int, List[dict]]:
    out: Dict[int, List[dict]] = {}
    for s in sessions:
        out.setdefault(s["cook_day"], []).append(s)
    return out
