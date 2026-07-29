"""Repair pass: re-fetch + re-parse the recipes that stored with empty
ingredients (wikitable / mislabeled-section pages the old parser missed) and
UPDATE them in place. add_recipe dedupes by title, so a plain re-import would
skip these — hence a direct UPDATE."""
import sqlite3
import time

from john_whisk import config, recipe_import as ri

config.IMPORT_RATE_LIMIT_S = 2.0


def main():
    conn = sqlite3.connect(config.RECIPES_DB_PATH)
    rows = conn.execute("SELECT id, title FROM recipes WHERE ingredients = '' OR ingredients IS NULL").fetchall()
    print(f"empty-ingredient recipes to repair: {len(rows)}", flush=True)

    id_by_page = {f"Cookbook:{title}": rid for rid, title in rows}
    pages = list(id_by_page)
    fixed = 0
    for i in range(0, len(pages), 50):
        batch = pages[i:i + 50]
        for page, wt in ri._fetch_wikitext_batch(batch).items():
            rec = ri.parse_wikibook_recipe(wt, page)
            if rec and rec["ingredients"]:
                conn.execute("UPDATE recipes SET ingredients = ? WHERE id = ?",
                             (rec["ingredients"], id_by_page[page]))
                fixed += 1
        conn.commit()
        print(f"  ...processed {min(i + 50, len(pages))}/{len(pages)}, fixed {fixed}", flush=True)
        time.sleep(config.IMPORT_RATE_LIMIT_S)

    still_empty = conn.execute("SELECT COUNT(*) FROM recipes WHERE ingredients = '' OR ingredients IS NULL").fetchone()[0]
    print(f"DONE: fixed {fixed}; still empty: {still_empty}", flush=True)


if __name__ == "__main__":
    main()
