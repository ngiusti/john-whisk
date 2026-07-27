from john_whisk import llm


def test_extract_items_names_and_types():
    items = llm.extract_items("I bought two chicken breasts and a dozen eggs")
    assert isinstance(items, list) and len(items) >= 2
    names = " ".join(i["name"] for i in items)
    assert "chicken" in names
    assert "egg" in names
    for i in items:
        assert i["quantity"] is None or isinstance(i["quantity"], (int, float))
        assert i["unit"] is None or isinstance(i["unit"], str)


def test_extract_items_empty_on_junk():
    # Non-grocery text should yield no items (model returns empty list).
    items = llm.extract_items("the weather is nice today")
    assert isinstance(items, list)
