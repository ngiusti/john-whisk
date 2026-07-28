import re

from john_whisk import db, llm, restrictions, ratings, equipment

# Lead-in phrases that precede the item(s) in a "we're out of X" utterance.
# Stored already normalized (letters/digits/space only) so contractions like
# "we're" -> "we re" match after the same normalization is applied to speech.
_REMOVE_LEADINS = [
    "used the last of the", "used the last of", "used all of the",
    "used all the", "used the rest of the", "used the rest of",
    "we re all out of", "we re out of", "i m out of", "im out of",
    "all out of", "ran out of", "run out of", "used up", "used the last",
    "no more", "throw out the", "throw out", "threw out the", "threw out",
    "remove the", "remove", "delete the", "delete", "all gone", "out of",
]
# Words to drop from the edges of a parsed item name.
_REMOVE_FILLERS = {"the", "of", "some", "a", "an", "my", "any", "left", "please"}


def parse_removed_names(text: str) -> list:
    """Pull the item name(s) out of a removal utterance, deterministically —
    no LLM (per the architecture note: keep pure intent+data ops out of the
    hot path). Returns a list of lowercase names, possibly multiword."""
    t = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    # Consume as much lead-in as possible: pick the match that ends latest.
    best_end = -1
    for lead in _REMOVE_LEADINS:
        idx = t.find(lead)
        if idx != -1 and idx + len(lead) > best_end:
            best_end = idx + len(lead)
    if best_end == -1:
        return []
    tail = t[best_end:].strip()
    names = []
    for chunk in tail.split(" and "):
        words = [w for w in chunk.split() if w not in _REMOVE_FILLERS]
        name = " ".join(words).strip()
        if name:
            names.append(name)
    return names


# Question scaffolding to strip from ANYWHERE in a pantry query, so the item or
# category term is found whether it's mid-sentence ("what kind of PASTA do I
# have") or trailing ("do we have any SAUCES"). "and" is kept as a separator.
_QUERY_SCAFFOLD = {
    "what", "kind", "sort", "of", "do", "does", "did", "i", "we", "you",
    "have", "has", "had", "got", "get", "is", "there", "are", "any", "some",
    "the", "a", "an", "my", "our", "more", "left", "still", "in", "stock",
    "pantry", "fridge", "kitchen",
}


def parse_queried_names(text: str) -> list:
    """Pull the queried item/category term(s) out of a pantry question,
    deterministically (no LLM), by removing question scaffolding. Returns
    lowercase terms, possibly multiword, split on "and"."""
    t = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    kept = [w for w in t.split() if w == "and" or w not in _QUERY_SCAFFOLD]
    names = []
    for chunk in " ".join(kept).split(" and "):
        name = chunk.strip()
        if name:
            names.append(name)
    return names


def _format_item(item) -> str:
    """'2 eggs', '12 eggs', or just 'spinach' when quantity is unknown."""
    q = item["quantity"]
    name = item["name"]
    if q is None:
        return name
    q_str = str(int(q)) if float(q).is_integer() else str(q)
    return f"{q_str} {name}"


def _join(parts) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] + " and " + parts[1]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def add_from_text(text: str) -> str:
    items = llm.extract_items(text)
    if not items:
        return "I didn't catch what you bought. Try again."
    db.add_items(items)
    return "Added " + _join([_format_item(i) for i in items]) + "."


def list_stock() -> str:
    """Read the pantry back to the user straight from the DB (no LLM)."""
    stock = db.get_inventory()
    if not stock:
        return "Your pantry's empty. Tell me what you bought first."
    return "You have " + _join([_format_item(i) for i in stock]) + "."


def check(text: str) -> str:
    """Answer "do we have X?" straight from the DB, never from the model — so it
    cannot invent inventory. Each term matches by item NAME or CATEGORY, so
    "sauces" / "what kind of pasta" list the tagged items. Falls back to a full
    list if nothing was parsed."""
    terms = parse_queried_names(text)
    if not terms:
        return list_stock()
    have = []
    missing = []
    for term in terms:
        matches = db.match_query(term)
        if matches:
            for name in matches:
                if name not in have:          # de-dupe (name + its category can both hit)
                    have.append(name)
        else:
            missing.append(term)
    if have and not missing:
        return "Yes, you have " + _join(have) + "."
    if missing and not have:
        return "No, I don't see any " + _join(missing) + " on your list."
    return "You have " + _join(have) + ", but no " + _join(missing) + "."


def remove_from_text(text: str) -> str:
    """Handle "we're out of X": drop the item(s) from the pantry and confirm."""
    names = parse_removed_names(text)
    if not names:
        return "I didn't catch what you ran out of. Try again."
    removed = db.remove_items(names)
    if not removed:
        return "You didn't have any " + _join(names) + " logged anyway."
    return "Okay, took " + _join(removed) + " off your list."


def substitute(title: str, step: str, ingredient: str) -> str:
    """Suggest a substitute for a missing ingredient, grounded in the real
    pantry (so it prefers what the cook has). Never invents inventory."""
    stock = db.get_inventory()
    pantry = ", ".join(_format_item(i) for i in stock) if stock else "nothing yet"
    return (llm.suggest_substitution(pantry, title, step, ingredient)
            or "Sorry, I couldn't think of a substitute right now.")


def ask_general(text: str) -> str:
    """General Q&A fallback, grounded with the real pantry so the model can't
    invent inventory even for phrasings that slip past the check intent."""
    stock = db.get_inventory()
    pantry = ", ".join(_format_item(i) for i in stock) if stock else ""
    return llm.ask_grounded(text, pantry) or "Sorry, my brain hiccupped. Try again."


def suggest(text: str) -> str:
    stock = db.get_inventory()
    if not stock:
        return "Your pantry's empty. Tell me what you bought first."
    stock_str = ", ".join(_format_item(i) for i in stock)
    # Pass ONLY the logged pantry; llm.suggest_recipe enforces the no-invention rule.
    # Active dietary restrictions + learned likes/dislikes are prepended so the
    # model avoids restricted/disliked recipes and favors what you enjoy.
    request = (restrictions.prompt_clause() + ratings.preference_clause()
               + equipment.prompt_clause() + text)
    return llm.suggest_recipe(stock_str, request) or "Sorry, my brain hiccupped. Try again."
