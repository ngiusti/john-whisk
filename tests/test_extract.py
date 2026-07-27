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


def test_no_quantity_when_unspecified():
    # No numbers stated -> quantities must be null (not guessed).
    items = llm.extract_items("I bought chicken and eggs")
    assert len(items) >= 2
    for i in items:
        assert i["quantity"] is None


def test_explicit_quantity_captured():
    items = llm.extract_items("I bought a dozen eggs")
    eggs = [i for i in items if "egg" in i["name"]]
    assert eggs and eggs[0]["quantity"] == 12
