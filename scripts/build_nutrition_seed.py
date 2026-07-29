"""Regenerate/extend data/nutrition.json from USDA FoodData Central (public
domain). NOT run at runtime. Download the SR Legacy CSV bundle from
https://fdc.nal.usda.gov/download-datasets.html, then for each curated common
food pull its per-100g calories/protein/carbs/fat from food_nutrient.csv and
household weights from food_portion.csv, and write the JSON shape used by
data/nutrition.json (see nutrition._load_seed). Left as a documented maintainer
tool; the hand-curated seed already ships with the app."""

if __name__ == "__main__":
    raise SystemExit("Maintainer tool: see module docstring; not yet implemented.")
