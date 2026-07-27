from john_whisk import db, llm


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


def suggest(text: str) -> str:
    stock = db.get_inventory()
    if not stock:
        return "Your pantry's empty. Tell me what you bought first."
    stock_str = ", ".join(_format_item(i) for i in stock)
    prompt = (
        f"I have these items in my kitchen: {stock_str}. {text} "
        "Suggest one or two quick recipe ideas that mostly use these items. "
        "You may mention one or two common items I'd need to add."
    )
    return llm.ask(prompt) or "Sorry, my brain hiccupped. Try again."
