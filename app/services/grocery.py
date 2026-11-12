"""Build one consolidated shopping list from a plan's meals. Pure functions."""
from collections import Counter, OrderedDict
from typing import Dict, Iterable, List


def norm(name: str) -> str:
    n = " ".join(name.casefold().split())
    return n


def item_key(name: str, unit: str) -> str:
    return f"{norm(name)}|{(unit or '').lower().strip()}"


def build_list(meals: Iterable[dict]) -> List[Dict]:
    """Merge duplicate ingredients (same name + unit) by summing quantities and costs."""
    merged: "OrderedDict[str, Dict]" = OrderedDict()
    for m in meals:
        for i in m["ingredients"]:
            k = item_key(i["name"], i.get("unit", ""))
            it = merged.setdefault(k, dict(key=k, name=norm(i["name"]), unit=(i.get("unit") or "").lower().strip(),
                                           quantity=0.0, cost=0.0, sections=Counter(), meals=[]))
            it["quantity"] += i["quantity"]
            it["cost"] += i["cost"]
            it["sections"][i.get("section", "other")] += 1
            if m["name"] not in it["meals"]:
                it["meals"].append(m["name"])
    out = []
    for it in merged.values():
        it["quantity"] = round(it["quantity"], 2)
        it["cost"] = round(it["cost"], 2)
        it["section"] = it.pop("sections").most_common(1)[0][0]
        out.append(it)
    return sorted(out, key=lambda x: x["name"])


def _same_food(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    return a == b or a.rstrip("s") == b.rstrip("s")


def apply_pantry(items: List[Dict], pantry: Iterable[dict]) -> List[Dict]:
    """Remove or reduce items the user already has.

    * pantry entry with no quantity  -> "I have it": item is dropped entirely.
    * quantity + SAME unit           -> subtract; item stays only for the shortfall.
    * quantity + different unit      -> can't convert units, so keep the full amount and note what they have.
    """
    pantry = list(pantry)
    out = []
    for it in items:
        it = dict(it)
        matches = [p for p in pantry if _same_food(p["name"], it["name"])]
        if matches:
            if any(p.get("quantity") is None for p in matches):
                continue
            same_unit = [p for p in matches if (p.get("unit") or "").lower().strip() == it["unit"].lower()]
            if same_unit:
                available = sum(p["quantity"] for p in same_unit)
                need = round(it["quantity"] - available, 2)
                if need <= 0:
                    continue
                it["cost"] = round(it["cost"] * need / it["quantity"], 2)
                it["have"] = f"{available:g} {it['unit']}".strip()
                it["quantity"] = need
            else:
                it["have"] = ", ".join(f"{p['quantity']:g} {p.get('unit', '')}".strip() for p in matches) + " (different unit)"
        out.append(it)
    return out


SECTION_ORDER = ["produce", "dairy", "meat", "seafood", "bakery", "frozen", "pantry", "other"]
SECTION_LABEL = {"produce": "Produce", "dairy": "Dairy & eggs", "meat": "Meat", "seafood": "Seafood",
                 "bakery": "Bakery", "frozen": "Frozen", "pantry": "Pantry", "other": "Other"}


def group_by_section(items: List[Dict]) -> List[Dict]:
    """[{section, label, entries}] in store-walk order; every item appears in exactly one section."""
    buckets: Dict[str, List[Dict]] = {s: [] for s in SECTION_ORDER}
    for it in items:
        buckets[it["section"] if it["section"] in buckets else "other"].append(it)
    return [dict(section=s, label=SECTION_LABEL[s], entries=buckets[s]) for s in SECTION_ORDER if buckets[s]]
