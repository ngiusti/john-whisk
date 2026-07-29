"""Importers that fill the recipe store. Reads schema.org/Recipe structured
data (what sites publish for machines) — never scrapes prose. The whole-site
crawler obeys robots.txt, rate-limits, caps the count, and stays same-domain.
Intended for openly-licensed datasets, individual recipe URLs, and sites that
permit it or that you own. Import is a CLI/admin action, never voice-triggered."""
import json
import re
import time
import logging
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests

from john_whisk import config, recipes

log = logging.getLogger("john_whisk.recipe_import")

_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


# --- schema.org/Recipe parsing (pure; no network) -------------------------

def _extract_jsonld(html):
    out = []
    for m in _JSONLD_RE.finditer(html or ""):
        try:
            out.append(json.loads(m.group(1).strip()))
        except (ValueError, TypeError):
            continue
    return out


def _candidates(data):
    """Yield every dict inside a JSON-LD blob (handles lists and @graph)."""
    stack = [data]
    while stack:
        d = stack.pop()
        if isinstance(d, list):
            stack.extend(d)
        elif isinstance(d, dict):
            if isinstance(d.get("@graph"), list):
                stack.extend(d["@graph"])
            yield d


def _is_recipe(d):
    t = d.get("@type")
    return "Recipe" in t if isinstance(t, list) else t == "Recipe"


def _instructions_to_steps(instr):
    """Normalize schema.org recipeInstructions into a flat list of step strings."""
    if not instr:
        return []
    if isinstance(instr, str):
        s = instr.strip()
        if "\n" in s:                                   # newline-separated steps
            return [ln.strip() for ln in s.splitlines() if ln.strip()]
        return [x.strip() for x in re.split(r"(?<=[.!?])\s+", s) if x.strip()]
    steps = []
    if isinstance(instr, list):
        for item in instr:
            if isinstance(item, str):
                steps.append(item.strip())
            elif isinstance(item, dict):
                if item.get("@type") == "HowToSection":
                    steps.extend(_instructions_to_steps(item.get("itemListElement")))
                else:
                    txt = item.get("text") or item.get("name")
                    if txt:
                        steps.append(str(txt).strip())
    return [s for s in steps if s]


def _normalize(d, source):
    title = d.get("name")
    if not isinstance(title, str) or not title.strip():
        return None
    ing = d.get("recipeIngredient") or d.get("ingredients") or []
    if isinstance(ing, str):
        ing = [ing]
    ingredients = ", ".join(str(i).strip() for i in ing if str(i).strip())
    steps = _instructions_to_steps(d.get("recipeInstructions"))
    if not steps:
        return None
    return {"title": title.strip(), "ingredients": ingredients,
            "steps": steps, "source": source}


def parse_recipe_html(html, source=""):
    """Return {title, ingredients, steps, source} from a page's schema.org
    Recipe data, or None if the page has no usable recipe."""
    for data in _extract_jsonld(html):
        for d in _candidates(data):
            if _is_recipe(d):
                rec = _normalize(d, source)
                if rec:
                    return rec
    return None


def parse_recipe_page(url):
    try:
        r = requests.get(url, headers={"User-Agent": config.IMPORT_USER_AGENT}, timeout=15)
        r.raise_for_status()
        return parse_recipe_html(r.text, source=url)
    except (requests.RequestException, ValueError):
        return None


# --- importers ------------------------------------------------------------

def import_url(url):
    """Import a single recipe page into the store. Returns True if added."""
    rec = parse_recipe_page(url)
    if not rec:
        return False
    return recipes.add_recipe(rec["title"], rec["ingredients"], rec["steps"],
                              source=rec.get("source", url))


def import_dataset(path):
    """Bulk-load an openly-licensed recipe dataset (JSON list of
    {title, ingredients, instructions}) into the store. Returns count added."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    added = 0
    for r in data:
        title = r.get("title") or r.get("name")
        if not title:
            continue
        ing = r.get("ingredients") or r.get("recipeIngredient") or []
        steps = _instructions_to_steps(
            r.get("instructions") or r.get("steps") or r.get("recipeInstructions"))
        if not steps:
            continue
        if recipes.add_recipe(title, ing, steps, source=r.get("source", "dataset")):
            added += 1
    return added


def import_themealdb():
    """Import TheMealDB's free public catalog via its documented developer API
    (intended for building recipe apps). Iterates the a-z listing, which returns
    full recipes. Returns count added. Rate-limited between letters."""
    added, seen = 0, set()
    for ch in "abcdefghijklmnopqrstuvwxyz":
        try:
            r = requests.get(
                f"https://www.themealdb.com/api/json/v1/1/search.php?f={ch}",
                headers={"User-Agent": config.IMPORT_USER_AGENT}, timeout=20)
            meals = (r.json() or {}).get("meals") or []
        except (requests.RequestException, ValueError):
            meals = []
        for m in meals:
            mid = m.get("idMeal")
            if mid in seen:
                continue
            seen.add(mid)
            title = m.get("strMeal")
            if not title:
                continue
            ingredients = []
            for i in range(1, 21):
                name = (m.get(f"strIngredient{i}") or "").strip()
                measure = (m.get(f"strMeasure{i}") or "").strip()
                if name:
                    ingredients.append((measure + " " + name).strip())
            steps = _instructions_to_steps(m.get("strInstructions"))
            if not steps:
                continue
            if recipes.add_recipe(title, ingredients, steps,
                                  source=m.get("strSource") or "themealdb.com"):
                added += 1
        time.sleep(config.IMPORT_RATE_LIMIT_S)
    return added


# --- Wikibooks Cookbook (CC-BY-SA) via the MediaWiki API ------------------
# The MediaWiki API is an intended programmatic interface and the Cookbook is
# openly licensed (CC BY-SA, attribution kept in `source`). Recipe pages use a
# very regular wikitext shape: "== Ingredients ==" with "*" bullets and
# "== Procedure ==" with "#" numbered steps (ingredient sub-sections like
# "=== Cake ===" stay under Ingredients). Non-recipe pages (no steps) drop out.

WIKIBOOKS_API = "https://en.wikibooks.org/w/api.php"
WIKIBOOKS_COOKBOOK_NS = 102          # the "Cookbook:" namespace

# Curated import plan: cuisine/baking categories the library should cover.
# Tagged categories are imported FIRST so their tags win over the general pull
# (add_recipe dedupes by title; the first insert keeps its tags).
WIKIBOOKS_TARGETS = [
    ("Egyptian recipes", "egyptian"),
    ("Greek recipes", "mediterranean, greek"),
    ("Italian recipes", "mediterranean, italian"),
    ("Lebanese recipes", "mediterranean, lebanese"),
    ("Turkish recipes", "mediterranean, turkish"),
    ("Moroccan recipes", "mediterranean, moroccan"),
    ("Spanish recipes", "mediterranean, spanish"),
    ("Israeli recipes", "mediterranean, israeli"),
    ("Syrian recipes", "mediterranean, syrian"),
    ("Tunisian recipes", "mediterranean, tunisian"),
    ("Cypriot recipes", "mediterranean, cypriot"),
    ("Portuguese recipes", "mediterranean, portuguese"),
    ("Bread recipes", "baking, bread"),
    ("Bread flour recipes", "baking, bread"),
    ("Cookie recipes", "baking, cookie"),
    ("Dessert recipes", "baking, dessert"),
    ("Cake recipes", "baking, cake"),
    ("Pastry recipes", "baking, pastry"),
    ("Pie recipes", "baking, pie"),
    ("Muffin recipes", "baking, muffin"),
]

_WIKILINK_PIPE = re.compile(r"\[\[[^\]|]*\|([^\]]+)\]\]")   # [[X|shown]] -> shown
_WIKILINK = re.compile(r"\[\[([^\]|]+)\]\]")                # [[Cookbook:Y]] -> Y
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_REF = re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL | re.IGNORECASE)
_SELFREF = re.compile(r"<ref[^>]*/>", re.IGNORECASE)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_HEADER = re.compile(r"^(={2,})\s*(.+?)\s*\1\s*$")

_ING_HDR = ("ingredient",)
_STEP_HDR = ("procedure", "method", "direction", "preparation",
             "instruction", "step", "cooking")


def _clean_wikitext(s):
    """Strip wiki markup from a fragment: links, templates, refs, bold/italic,
    stray HTML — leaving human-readable text. `[[Cookbook:Rice|rice]]` -> rice,
    `[[Cookbook:Boiling]]` -> Boiling."""
    s = _COMMENT.sub("", s)
    s = _REF.sub("", s)
    s = _SELFREF.sub("", s)
    s = _TEMPLATE.sub("", s)
    s = _WIKILINK_PIPE.sub(r"\1", s)
    s = _WIKILINK.sub(lambda m: m.group(1).rsplit(":", 1)[-1], s)   # drop "Cookbook:"
    s = s.replace("'''", "").replace("''", "")
    s = _TAG.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_wikibook_recipe(wikitext, title, source="", tags=""):
    """Parse a Wikibooks Cookbook page's wikitext into
    {title, ingredients, steps, source, tags}, or None if it has no steps
    (i.e. it is an ingredient/technique page, not a recipe). Only level-2
    headers switch the section; level-3 sub-headers keep the current section
    so ingredient sub-groups (Cake / Syrup) are all collected."""
    mode = None
    ingredients, steps, step_bullets = [], [], []
    in_table = expect_cell = False
    for raw in (wikitext or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _HEADER.match(line)
        if m:
            if len(m.group(1)) == 2:                     # a top-level section
                name = m.group(2).lower()
                if any(k in name for k in _ING_HDR):
                    mode = "ing"
                elif any(k in name for k in _STEP_HDR):
                    mode = "step"
                else:
                    mode = None
                in_table = expect_cell = False
            continue                                     # sub-headers keep mode
        if mode == "ing":
            # Ingredient wikitable: the first cell of each data row is the name.
            if line.startswith("{|"):
                in_table, expect_cell = True, True
                continue
            if line.startswith("|}"):
                in_table = False
                continue
            if in_table:
                if line.startswith("|-"):                # next row
                    expect_cell = True
                elif line.startswith("!") or line.startswith("|+"):
                    pass                                 # header / caption cell
                elif line.startswith("|") and expect_cell:
                    item = _clean_wikitext(line[1:].split("||")[0].strip())
                    if item:
                        ingredients.append(item)
                    expect_cell = False                  # first cell only
                continue
            if line.startswith("*"):
                item = _clean_wikitext(line.lstrip("*").strip())
                if item:
                    ingredients.append(item)
        elif mode == "step":
            if line.startswith("#"):
                item = _clean_wikitext(line.lstrip("#").strip())
                if item:
                    steps.append(item)
            elif line.startswith("*"):
                # bullets in a step-labeled section can be mislabeled ingredients
                item = _clean_wikitext(line.lstrip("*").strip())
                if item:
                    step_bullets.append(item)
    if not ingredients and step_bullets:                 # mislabeled-section rescue
        ingredients = step_bullets
    if not steps:
        return None
    clean_title = title.split(":", 1)[-1].strip() if ":" in title else title.strip()
    return {"title": clean_title, "ingredients": ", ".join(ingredients),
            "steps": steps, "source": source, "tags": tags}


def _wiki_api(params, _tries=6):
    """One MediaWiki API GET, hardened for a bulk run against Wikimedia's rate
    limits: retry with exponential backoff, honor a `Retry-After` header on
    429/503, and send the courtesy `maxlag` param. An API "error" payload
    (maxlag/ratelimited) is treated as a retryable failure, NOT as success —
    so a throttle never silently looks like an empty result."""
    p = {"format": "json", "formatversion": "2", "maxlag": "5"}
    p.update(params)
    delay = 2.0
    for attempt in range(_tries):
        retry_after = None
        try:
            r = requests.get(WIKIBOOKS_API, params=p,
                             headers={"User-Agent": config.IMPORT_USER_AGENT}, timeout=30)
            if r.status_code in (429, 503):
                retry_after = r.headers.get("Retry-After")
                raise requests.RequestException(f"HTTP {r.status_code} (throttled)")
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise requests.RequestException(f"API error: {data['error']}")
            return data
        except (requests.RequestException, ValueError):
            if attempt == _tries - 1:
                raise
            wait = delay
            if retry_after:
                try:
                    wait = max(wait, float(retry_after))
                except ValueError:
                    pass
            time.sleep(wait)
            delay = min(delay * 2, 30.0)
    return {}


def _wikibooks_category_titles(category, cap=None):
    """Every Cookbook: page title in a Wikibooks category, following pagination.
    Missing/empty categories yield an empty list; a hard API failure (after
    retries) is logged, not silently treated as 'done'."""
    titles, cont = [], {}
    while True:
        try:
            data = _wiki_api({"action": "query", "list": "categorymembers",
                              "cmtitle": f"Category:{category}", "cmlimit": "500",
                              "cmtype": "page", "cmnamespace": WIKIBOOKS_COOKBOOK_NS,
                              **cont})
        except (requests.RequestException, ValueError):
            log.warning("category listing failed for %s (kept %d so far)",
                        category, len(titles))
            break
        for mem in data.get("query", {}).get("categorymembers", []):
            t = mem.get("title", "")
            if t.startswith("Cookbook:"):
                titles.append(t)
        cont = data.get("continue", {})
        if not cont or (cap and len(titles) >= cap):
            break
        time.sleep(config.IMPORT_RATE_LIMIT_S)
    return titles[:cap] if cap else titles


def _wikibooks_cookbook_titles(cap=None):
    """Every page title in the Cookbook namespace (recipes + non-recipes; the
    parser filters non-recipes out). The widest volume source."""
    titles, cont = [], {}
    while True:
        try:
            data = _wiki_api({"action": "query", "list": "allpages",
                              "apnamespace": WIKIBOOKS_COOKBOOK_NS, "aplimit": "500",
                              **cont})
        except (requests.RequestException, ValueError):
            break
        for pg in data.get("query", {}).get("allpages", []):
            t = pg.get("title", "")
            if t:
                titles.append(t)
        cont = data.get("continue", {})
        if not cont or (cap and len(titles) >= cap):
            break
        time.sleep(config.IMPORT_RATE_LIMIT_S)
    return titles[:cap] if cap else titles


def _fetch_wikitext_batch(titles):
    """{title: wikitext} for up to 50 page titles in one API call."""
    if not titles:
        return {}
    out = {}
    try:
        data = _wiki_api({"action": "query", "prop": "revisions",
                          "rvslots": "main", "rvprop": "content",
                          "titles": "|".join(titles)})
    except (requests.RequestException, ValueError):
        log.warning("wikitext fetch failed for a batch of %d titles", len(titles))
        return {}
    for pg in data.get("query", {}).get("pages", []):
        if pg.get("missing"):
            continue
        revs = pg.get("revisions") or []
        content = (revs[0].get("slots", {}).get("main", {}).get("content")
                   if revs else None)
        if content:
            out[pg["title"]] = content
    return out


def _import_titles(titles, tags=""):
    """Fetch + parse + store a list of Cookbook page titles. Returns count added."""
    added = 0
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        for title, wt in _fetch_wikitext_batch(batch).items():
            rec = parse_wikibook_recipe(
                wt, title,
                source=f"en.wikibooks.org Cookbook (CC BY-SA): {title}", tags=tags)
            if rec and recipes.add_recipe(rec["title"], rec["ingredients"],
                                          rec["steps"], source=rec["source"], tags=tags):
                added += 1
        time.sleep(config.IMPORT_RATE_LIMIT_S)
    return added


def import_wikibooks_category(category, tags="", cap=None):
    """Import all recipes in one Wikibooks Cookbook category. Returns count added."""
    added = _import_titles(_wikibooks_category_titles(category, cap=cap), tags=tags)
    log.info("import_wikibooks_category %s -> %s added", category, added)
    return added


def import_wikibooks_all(include_general=True, general_cap=None):
    """Import the curated cuisine/baking targets (tagged) first, then the master
    Category:Recipes for volume (deduped by title). Returns {label: count_added}."""
    results = {}
    for category, tags in WIKIBOOKS_TARGETS:
        results[category] = import_wikibooks_category(category, tags=tags)
    if include_general:
        results["Recipes"] = _import_titles(
            _wikibooks_category_titles("Recipes", cap=general_cap), tags="")
    return results


# --- guarded whole-site crawl ---------------------------------------------

def _discover_urls(base):
    """Same-domain page URLs from the site's sitemap.xml."""
    urls = []
    try:
        r = requests.get(urljoin(base, "/sitemap.xml"),
                         headers={"User-Agent": config.IMPORT_USER_AGENT}, timeout=15)
        if r.ok:
            urls = re.findall(r"<loc>(.*?)</loc>", r.text)
    except requests.RequestException:
        pass
    dom = urlparse(base).netloc
    return [u.strip() for u in urls if urlparse(u.strip()).netloc == dom]


def _robots_for(base):
    rp = robotparser.RobotFileParser()
    rp.set_url(urljoin(base, "/robots.txt"))
    try:
        rp.read()
    except Exception:
        pass
    return rp


def _allowed(rp, url):
    try:
        return rp.can_fetch(config.IMPORT_USER_AGENT, url)
    except Exception:
        return True


def import_site(base_url, max_recipes=None):
    """Crawl a site's sitemap for recipes, obeying robots.txt, rate-limiting,
    same-domain-only, capped at max_recipes. Returns a summary dict (nothing is
    silently dropped — skips are counted)."""
    max_recipes = max_recipes or config.IMPORT_MAX_RECIPES
    urls = _discover_urls(base_url)
    rp = _robots_for(base_url)
    added = skipped_robots = skipped_parse = 0
    for url in urls:
        if added >= max_recipes:
            break
        if not _allowed(rp, url):
            skipped_robots += 1
            continue
        time.sleep(config.IMPORT_RATE_LIMIT_S)   # be a good citizen
        if import_url(url):
            added += 1
        else:
            skipped_parse += 1
    result = {"considered": len(urls), "added": added,
              "skipped_robots": skipped_robots, "skipped_parse": skipped_parse}
    log.info("import_site %s -> %s", base_url, result)
    return result
