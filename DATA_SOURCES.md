# Ingredient data and limits

Nutrients are computed from the checked-in USDA FoodData Central SR Legacy snapshot in `app/data/ingredients.json`. It contains the source FDC identifier, food description, per-100-gram energy/protein, publication date and source URL for every supported ingredient. The source ZIP SHA-256 is recorded for reproducibility.

Source: U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, SR Legacy April 2018 release, published April 2019. Download: https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip. Licensing/API guide: https://fdc.nal.usda.gov/api-guide/. USDA data are public domain/CC0.

Recipe gram measures are explicit assumptions, not independently measured facts. Rice is measured cooked; oats, lentils and pasta are dry. Edible fruit sizes, slices, scoops, cans and blocks are fixed in the snapshot and displayed for review. Brand, preparation and edible yield change nutrition. These are sourced estimates, not medical guarantees or a substitute for product allergen labels.

The original pea-protein recipe was renamed to soy-protein smoothie because the selected USDA record describes soy protein. The app does not silently use soy data for a pea ingredient. User dietary exclusions still apply.

The live model selects approved recipe names and slots. The server supplies recipe ingredients, steps, nutrients and reference costs. Unknown names/units are rejected rather than supplied with fabricated values. Existing historical/pinned recipes retain their recorded content.

Grocery prices are separate from USDA nutrient data. Built-in prices are labelled demo estimates. User-entered local package prices include their own source and observation date; they are not automatically refreshed store prices.
