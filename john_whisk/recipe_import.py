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
