"""Schedule batch-prep blocks on days with spare time. Pure functions, no DB."""
from typing import Dict, List

MIN_SPARE = 20  # a day needs at least this many spare minutes to host a prep block
MAX_BLOCKS = 2
HEAVY = 20  # meals needing at least this many cook minutes are worth prepping for
LOOKAHEAD = 3  # prep helps meals up to this many days later


def prep_blocks(meals: List[dict], days: List[dict]) -> List[Dict]:
    """meals: dicts with day/name/cook_minutes. days: dicts with weekday/minutes/busy/skipped.

    Returns [{"day", "minutes", "meals": [names]}]. A block only lands on a day that is not busy, not skipped,
    and where (cooking that day + block) fits inside the day's available minutes.
    """
    cooked = {d["weekday"]: 0 for d in days}
    for m in meals:
        cooked[m["day"]] = cooked.get(m["day"], 0) + m["cook_minutes"]
    spare = {}
    for d in days:
        if d.get("busy") or d.get("skipped"):
            continue
        s = d["minutes"] - cooked.get(d["weekday"], 0)
        if s >= MIN_SPARE:
            spare[d["weekday"]] = s
    heavy = [m for m in meals if m["cook_minutes"] >= HEAVY]
    blocks: List[Dict] = []
    assigned = set()
    for day in sorted(spare, key=lambda w: (-spare[w], w)):
        if len(blocks) >= MAX_BLOCKS:
            break
        targets = [m for m in heavy if day < m["day"] <= day + LOOKAHEAD and id(m) not in assigned]
        if not targets:
            continue
        for m in targets:
            assigned.add(id(m))
        minutes = min(spare[day], 15 + 10 * len(targets), 60)
        blocks.append({"day": day, "minutes": minutes, "meals": [m["name"] for m in targets]})
    return sorted(blocks, key=lambda b: b["day"])
