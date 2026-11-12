# Ingredient data and limits

Nutrients are computed from the checked-in USDA FoodData Central SR Legacy snapshot in `app/data/ingredients.json`. It contains the source FDC identifier, food description, per-100-gram energy/protein, publication date and source URL for every supported ingredient. The source ZIP SHA-256 is recorded for reproducibility.

Source: U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, SR Legacy April 2018 release, published April 2019. Download: https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip. Licensing/API guide: https://fdc.nal.usda.gov/api-guide/. USDA data are public domain/CC0.

Recipe gram measures are explicit assumptions, not independently measured facts. Rice is measured cooked; oats, lentils and pasta are dry. Edible fruit sizes, slices, scoops, cans and blocks are fixed in the snapshot and displayed for review. Brand, preparation and edible yield change nutrition. These are sourced estimates, not medical guarantees or a substitute for product allergen labels.

The original pea-protein recipe was renamed to soy-protein smoothie because the selected USDA record describes soy protein. The app does not silently use soy data for a pea ingredient. User dietary exclusions still apply.

The live model selects approved recipe names and slots. The server supplies recipe ingredients, steps, nutrients and reference costs. Unknown names/units are rejected rather than supplied with fabricated values. Existing historical/pinned recipes retain their recorded content.

Grocery prices are separate from USDA nutrient data. Built-in prices are labelled demo estimates. User-entered local package prices include their own source and observation date; they are not automatically refreshed store prices.

## Planner quality expansion (November 12, 2026)

The catalog now has **118 sourced ingredients and 110 recipe templates** (45 new
ingredients and 56 new recipes). All 118 ingredients are used by actual recipes.
The new records were imported from the same USDA SR Legacy ZIP named above,
verified against SHA-256
`b80817294b8850530aaedf2e515c02593b1824f763a0ff356e5c2081643e6fd0`.
Each record keeps its exact USDA FDC ID, description, publication date and nutrients.

To reproduce the new nutrient mappings from that downloaded ZIP:

```bash
.venv/Scripts/python.exe -m scripts.import_expanded_nutrition "C:/path/to/FoodData_Central_sr_legacy_food_csv_2018-04.zip"
```

The import is deterministic and was checked to reproduce both checked-in data
files byte for byte. New quinoa, brown rice, bulgur, barley, millet, wild rice,
couscous, white beans and edamame use **cooked cup** measures. Other ingredient
measures remain as documented in each source record; oats, dry lentils and pasta
retain their existing dry measures. New seafood/pork ounces are raw edible weights.
Cooked grain equivalent package sizes assume preparation yields; they are not dry
cups of a retail bag. Fruit sizes, vegetable cup weights and grain yields remain
explicit approximations, so product labels and actual shopping quantities matter.

`app/data/package_prices.json` holds **121 explicit demo package offers**, with
76 previous offers frozen before expansion plus 45 new estimates. Adding a recipe
no longer changes the median price of an existing ingredient. These prices are
**not measured store quotes and do not come from USDA**. Local price entries
still override them. Source links on the price page retain their existing meaning.

`app/data/recipes_expanded.json` contains original recipe instructions and measured
ingredient assumptions, not externally sourced recipe text. Its calories and
protein are computed on load from the USDA records. The added poultry recipes
use a 165°F internal temperature; added pork uses 145°F and a three-minute rest;
added finfish uses 145°F. See USDA FSIS and FDA guidance:

- https://www.fsis.usda.gov/food-safety/safe-food-handling-and-preparation/meat-catfish/safe-minimum-internal-temperature-chart
- https://www.fda.gov/food/buy-store-serve-safe-food/safe-food-handling

Diet rules were extended for the new fish, bulgur, soy aliases and sesame foods.
Corn tortilla substitutions do not hide wheat elsewhere, and almond milk remains
excluded for nut allergies. These ingredient-name checks cannot certify a brand's
cross-contact/allergen labeling or halal certification.
