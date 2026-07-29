from john_whisk import router


def test_nutrition_query_classified():
    assert router.classify("how many calories in chicken alfredo") == "nutrition_query"
    assert router.classify("what are the macros in two eggs") == "nutrition_query"
    assert router.classify("nutrition facts for pad thai") == "nutrition_query"


def test_nutrition_query_does_not_shadow_recipe_query():
    assert router.classify("how many recipes do you have") == "recipe_query"


def test_nutrition_query_does_not_shadow_cook():
    assert router.classify("let's make chicken alfredo") == "cook"
