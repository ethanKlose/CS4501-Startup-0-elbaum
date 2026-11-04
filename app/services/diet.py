"""Single source of truth for what ingredients violate which restriction.

Used by the validators (to reject plans) and by the fake LLM (to avoid proposing bad meals).
Matching is by whole word so 'eggplant' is not 'egg' and 'butternut' is not 'butter'.
"""
import re
from typing import Dict, Iterable, List

MEAT = ["chicken", "beef", "pork", "turkey", "bacon", "sausage", "ham", "lamb", "steak", "veal", "meatball", "meatballs", "sirloin", "gelatin"]
FISH = ["fish", "salmon", "tuna", "cod", "tilapia", "anchovy", "anchovies", "sardine", "sardines", "trout", "halibut", "mahi"]
SHELLFISH = ["shrimp", "crab", "lobster", "clam", "clams", "mussel", "mussels", "scallop", "scallops", "prawn", "prawns", "oyster", "oysters"]
DAIRY = ["milk", "cheese", "cheddar", "mozzarella", "parmesan", "feta", "yogurt", "butter", "cream", "whey", "paneer", "ghee", "cheeses"]
EGG = ["egg", "eggs", "mayo", "mayonnaise"]
GLUTEN = ["wheat", "bread", "pasta", "spaghetti", "flour", "tortilla", "tortillas", "couscous", "barley", "rye", "bun", "bagel", "noodle", "noodles", "pita", "naan", "seitan", "farro", "granola", "soy sauce"]
NUTS = ["peanut", "peanuts", "almond", "almonds", "walnut", "walnuts", "cashew", "cashews", "pecan", "pecans", "hazelnut", "hazelnuts", "pistachio", "pistachios", "nut", "nuts"]
PORK_HALAL = ["pork", "bacon", "ham", "lard", "gelatin", "wine", "beer", "sausage"]

GROUPS: Dict[str, List[str]] = {
    "meat": MEAT, "fish": FISH, "seafood": FISH + SHELLFISH, "shellfish": SHELLFISH,
    "dairy": DAIRY, "egg": EGG, "eggs": EGG, "gluten": GLUTEN, "nuts": NUTS, "nut": NUTS,
    "pork": PORK_HALAL, "honey": ["honey"],
}

RESTRICTION_TERMS: Dict[str, List[str]] = {
    "vegetarian": MEAT + FISH + SHELLFISH,
    "vegan": MEAT + FISH + SHELLFISH + DAIRY + EGG + ["honey"],
    "gluten_free": GLUTEN,
    "dairy_free": DAIRY,
    "nut_allergy": NUTS,
    "shellfish_allergy": SHELLFISH,
    "egg_free": EGG,
    "halal": PORK_HALAL,
}

# Phrases that contain a flagged word but are not that thing.
SAFE_PHRASES = [
    "coconut milk", "almond milk", "oat milk", "soy milk", "rice milk", "peanut butter", "almond butter",
    "cocoa butter", "nut-free", "chicken broth", "gluten-free", "gluten free", "cream of tartar", "coconut cream",
    "butternut", "nutmeg", "coconut",
]
# 'almond milk' etc. are non-dairy but still contain nuts; handle by checking nut terms on the raw text.
NUT_SAFE_EXEMPT = ["nutmeg", "butternut", "coconut", "nut-free"]


def _clean(text: str, nuts: bool) -> str:
    t = text.lower()
    for p in SAFE_PHRASES:
        if nuts and p not in NUT_SAFE_EXEMPT:
            continue  # keep 'almond milk' visible to the nut check
        t = t.replace(p, " ")
    return t


def _hits(text: str, terms: Iterable[str], nuts: bool = False) -> List[str]:
    t = _clean(text, nuts)
    return sorted({w for w in terms if re.search(r"\b" + re.escape(w) + r"\b", t)})


def term_hits(text: str, term: str) -> List[str]:
    """Which words in `text` match a restriction key, food group, or literal ingredient."""
    term = term.lower().strip()
    if term in RESTRICTION_TERMS:
        words = RESTRICTION_TERMS[term]
        return _hits(text, words, nuts=term == "nut_allergy")
    if term in GROUPS:
        return _hits(text, GROUPS[term], nuts=term in ("nuts", "nut"))
    # literal ingredient: match singular/plural
    base = term[:-1] if term.endswith("s") and len(term) > 3 else term
    t = text.lower()
    return [term] if re.search(r"\b" + re.escape(base) + r"s?\b", t) else []


def meal_texts(meal: dict) -> List[str]:
    return [meal.get("name", "")] + [i.get("name", "") for i in meal.get("ingredients", [])]


def meal_violations(meal: dict, restrictions: Iterable[str], excluded: Iterable[str] = ()) -> List[str]:
    """Human-readable violations for one meal dict (empty list = fine)."""
    out = []
    for key in list(restrictions) + list(excluded):
        for text in meal_texts(meal):
            hits = term_hits(text, key)
            if hits:
                label = key.replace("_", " ")
                out.append(f"'{meal.get('name')}' contains '{text}' which violates '{label}'")
                break
    return out
