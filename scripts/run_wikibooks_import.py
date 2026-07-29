"""One-off admin driver: bulk-import Wikibooks Cookbook recipes (CC BY-SA) into
recipes.db, printing progress. Cuisine/baking targets first (tagged), then the
master Category:Recipes for volume. Run on the Pi:

    nohup venv/bin/python scripts/run_wikibooks_import.py > /tmp/wb_import.log 2>&1 &
"""
import sys

from john_whisk import config, recipe_import as ri, recipes

# MediaWiki rate-limits bulk API use; a gentler base rate plus the hardened
# retry/backoff in _wiki_api keeps the run reliable (idempotent, so re-running
# only fills gaps left by any throttling).
config.IMPORT_RATE_LIMIT_S = 2.5


def main():
    start = recipes.count()
    print(f"START recipes.count() = {start}", flush=True)

    for category, tags in ri.WIKIBOOKS_TARGETS:
        added = ri.import_wikibooks_category(category, tags=tags)
        print(f"  [{category}] +{added}  (total {recipes.count()})", flush=True)

    print("Now the master Category:Recipes for volume...", flush=True)
    titles = ri._wikibooks_category_titles("Recipes")
    print(f"  Category:Recipes has {len(titles)} pages to consider", flush=True)
    added = ri._import_titles(titles, tags="")
    print(f"  [Recipes] +{added}  (total {recipes.count()})", flush=True)

    end = recipes.count()
    print(f"DONE recipes.count() = {end}  (+{end - start} this run)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
