"""Quick post-import sanity check: total count, tag distribution, and a few
spot-checks that recipes parsed with real ingredients + steps."""
import collections
import sqlite3

from john_whisk import config, recipes


def main():
    print("TOTAL:", recipes.count())

    c = sqlite3.connect(config.RECIPES_DB_PATH)
    cnt = collections.Counter()
    for (tags,) in c.execute("SELECT tags FROM recipes WHERE tags != ''"):
        for part in tags.split(","):
            cnt[part.strip()] += 1
    print("TAG BUCKETS:", dict(cnt.most_common()))

    print("---- spot checks ----")
    for dish in ["Koshari", "Basbousa", "Baklava", "Hummus", "Falafel",
                 "Focaccia", "Shortbread", "Banana Bread", "Tabbouleh"]:
        r = recipes.find(dish)
        if r:
            print(f"  {dish}: '{r['title']}'  ing={len(r['ingredients'])}c  steps={len(r['steps'])}")
        else:
            print(f"  {dish}: not found")


if __name__ == "__main__":
    main()
