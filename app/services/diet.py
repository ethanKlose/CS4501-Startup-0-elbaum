"""Single source of truth for what ingredients violate which restriction.

Used by the validators (to reject plans) and by the fake LLM (to avoid proposing bad meals).
Matching is by whole word so 'eggplant' is not 'egg' and 'butternut' is not 'butter'.
"""
import re
from typing import Dict, Iterable, List

MEAT = ["chicken", "beef", "pork", "turkey", "bacon", "sausage", "ham", "lamb", "steak", "veal", "meatball", "meatballs", "sirloin", "gelatin"]
FISH = ["fish", "salmon", "tuna", "cod", "tilapia", "anchovy", "anchovies", "sardine", "sardines", "trout", "halibut", "mahi", "mackerel", "herring", "pollock", "haddock"]
SHELLFISH = ["shrimp", "crab", "lobster", "clam", "clams", "mussel", "mussels", "scallop", "scallops", "prawn", "prawns", "oyster", "oysters"]
DAIRY = ["milk", "cheese", "cheddar", "mozzarella", "parmesan", "feta", "yogurt", "butter", "cream", "whey", "paneer", "ghee", "cheeses"]
EGG = ["egg", "eggs", "mayo", "mayonnaise"]
GLUTEN = ["wheat", "bread", "pasta", "spaghetti", "flour", "tortilla", "tortillas", "couscous", "barley", "rye", "bun", "bagel", "noodle", "noodles", "pita", "naan", "seitan", "farro", "bulgur", "granola", "soy sauce"]
NUTS = ["peanut", "peanuts", "almond", "almonds", "walnut", "walnuts", "cashew", "cashews", "pecan", "pecans", "hazelnut", "hazelnuts", "pistachio", "pistachios", "nut", "nuts"]
PORK_HALAL = ["pork", "bacon", "ham", "lard", "gelatin", "wine", "beer", "sausage"]

GROUPS: Dict[str, List[str]] = {
    "red meat": ["beef", "pork", "lamb", "veal", "steak", "sirloin", "bacon", "ham"],
    "meat": MEAT, "fish": FISH, "seafood": FISH + SHELLFISH, "shellfish": SHELLFISH,
    "dairy": DAIRY, "egg": EGG, "eggs": EGG, "gluten": GLUTEN, "nuts": NUTS, "nut": NUTS,
    "pork": PORK_HALAL, "honey": ["honey"],
    "soy": ["soy", "edamame", "tofu", "tempeh"],
    "sesame": ["sesame", "tahini", "hummus"],
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
    "sesame_allergy": GROUPS["sesame"],
}

# Exempt only the specific word replaced by a known substitute. Removing a
# whole phrase for every restriction would hide nuts in almond milk, for example.
WORD_EXCEPTIONS = {
    "milk": ["coconut milk", "almond milk", "oat milk", "soy milk", "rice milk"],
    "butter": ["peanut butter", "almond butter", "cocoa butter"],
    "cream": ["cream of tartar", "coconut cream"],
    "nut": ["nut-free", "nut free"],
    "nuts": ["nut-free", "nut free"],
    "tortilla": ["corn tortilla", "corn tortillas"],
    "tortillas": ["corn tortilla", "corn tortillas"],
}


def _hits(text: str, terms: Iterable[str]) -> List[str]:
    hits = []
    for word in terms:
        t = text.lower()
        for phrase in WORD_EXCEPTIONS.get(word, []):
            t = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", t)
        if word in GLUTEN:
            # A labelled substitute exempts this food, not other ingredients.
            t = re.sub(r"\bgluten[- ]free\s+" + re.escape(word) + r"\b", " ", t)
        if re.search(r"\b" + re.escape(word) + r"\b", t):
            hits.append(word)
    return sorted(set(hits))


def term_hits(text: str, term: str) -> List[str]:
    """Which words in `text` match a restriction key, food group, or literal ingredient."""
    term = term.lower().strip()
    if term in RESTRICTION_TERMS:
        words = RESTRICTION_TERMS[term]
        return _hits(text, words)
    if term in GROUPS:
        return _hits(text, GROUPS[term])
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
