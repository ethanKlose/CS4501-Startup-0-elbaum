"""Build one consolidated shopping list from a plan's meals. Pure functions."""
from collections import Counter, OrderedDict
from typing import Dict, Iterable, List


def norm(name: str) -> str:
    n = " ".join(name.lower().split())
    return n


def item_key(name: str, unit: str) -> str:
    return f"{norm(name)}|{(unit or '').lower().strip()}"


def build_list(meals: Iterable[dict]) -> List[Dict]:
    """Merge duplicate ingredients (same name + unit) by summing quantities and costs."""
    merged: "OrderedDict[str, Dict]" = OrderedDict()
    for m in meals:
        for i in m["ingredients"]:
            k = item_key(i["name"], i.get("unit", ""))
            it = merged.setdefault(k, dict(key=k, name=norm(i["name"]), unit=(i.get("unit") or "").strip(),
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
