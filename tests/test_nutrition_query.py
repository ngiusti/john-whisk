from john_whisk import router


def test_nutrition_query_classified():
    assert router.classify("how many calories in chicken alfredo") == "nutrition_query"
    assert router.classify("what are the macros in two eggs") == "nutrition_query"
    assert router.classify("nutrition facts for pad thai") == "nutrition_query"


def test_nutrition_query_does_not_shadow_recipe_query():
    assert router.classify("how many recipes do you have") == "recipe_query"


def test_nutrition_query_does_not_shadow_cook():
    assert router.classify("let's make chicken alfredo") == "cook"


def test_nutrition_log_classified():
    assert router.classify("I ate two eggs") == "nutrition_log"
    assert router.classify("log two eggs and toast") == "nutrition_log"
    assert router.classify("I had a bagel") == "nutrition_log"


def test_nutrition_log_serving_not_cook():
    assert router.classify("I ate a serving of chicken alfredo") == "nutrition_log"


def test_nutrition_goal_classified():
    assert router.classify("set my calorie goal to 2000") == "nutrition_goal"
    assert router.classify("what are my goals") == "nutrition_goal"


def test_nutrition_goal_before_query_for_calories_goal():
    # "calories goal" must be a goal, not a nutrition_query (goal checked first)
    assert router.classify("set my calories goal to 2000") == "nutrition_goal"


def test_status_query_classified():
    assert router.classify("how am I doing today") == "nutrition_query"
