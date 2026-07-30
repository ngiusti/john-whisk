SUGGEST_TRIGGERS = [
    "what can i make", "what can i cook", "what should i", "suggest", "recipe",
    "what's for dinner", "whats for dinner", "ideas for dinner", "make with",
]
# Pantry expiration ("what's going bad / what should I use up"). Before suggest
# so "what should I use up" isn't swallowed by suggest's "what should i".
EXPIRING_TRIGGERS = [
    "going bad", "go bad", "going off", "gone off", "use up", "use it up",
    "about to expire", "expiring", "expire soon", "past their prime",
    "spoiling", "going to spoil", "what's going bad", "whats going bad",
]
# Time-based filtering ("what can I make in 20 minutes / something quick").
# Before suggest so a time budget isn't swallowed by suggest's "what can i make".
# "minute" catches "in N minutes"; "fast"/"how long" omitted (breakfast/duration).
QUICK_TRIGGERS = ["minute", "quick", "half an hour", "in an hour", "in a hurry"]
# Seasonal + budget modes. Before suggest so "what can I make on a budget"
# / "...that's in season" aren't swallowed by suggest's "what can i make".
SEASONAL_TRIGGERS = ["in season", "in-season", "seasonal", "this season"]
BUDGET_TRIGGERS = ["cheap", "budget", "inexpensive", "low cost", "low-cost",
                   "affordable", "frugal", "save money"]
# Questions about the STORED recipe library (answered from recipes.db, not the
# LLM). Placed before cook/suggest/check so "do you have a recipe for X" queries
# the library instead of the pantry, while "let's make X" stays a cook.
RECIPE_QUERY_TRIGGERS = [
    "do you have a recipe", "do we have a recipe", "got a recipe",
    "is there a recipe", "do you know a recipe", "what recipes", "which recipes",
    "how many recipes", "recipe for",
]
# Nutrition questions about a recipe or food, plus "how am I doing today" status.
# After recipe_query (so "how many recipes" stays a library query) and after cook.
NUTRITION_QUERY_TRIGGERS = [
    "calories", "macros", "how much protein", "how much fat", "how many carbs",
    "nutrition", "nutritional", "how am i doing", "what have i eaten",
    "what did i eat", "so far today", "eaten today",
]
# Set/query a daily nutrition goal. Checked BEFORE nutrition_query so
# "set my calories goal" isn't grabbed by the "calories" trigger.
NUTRITION_GOAL_TRIGGERS = ["goal", "target"]
# Log what was eaten. Before nutrition_query; "i ate a serving of X" must not be
# a cook. Trailing/leading spaces (the router pads the text) avoid substring hits.
NUTRITION_LOG_TRIGGERS = ["i ate", "i had", "i just ate", "i just had", "log "]
# Plan a meal: find the recipe and add MISSING ingredients to the grocery list
# (does not start cooking). Distinct from cook ("let's make X") — these are
# desire/intent phrasings the router's cook triggers don't cover.
PLAN_TRIGGERS = [
    "i would like to make", "i'd like to make", "i want to make",
    "i'm going to make", "im going to make", "planning to make", "plan to make",
    "what do i need to make", "what do i need for", "add ingredients for",
    "shop for",
]
# Meal-planning CALENDAR (schedule dishes onto dates / read the plan). Query is
# checked before Set (they share "on the menu"), and BOTH after grocery's `plan`
# (so "plan to make X" stays the grocery meal-planner). Before grocery/suggest.
PLAN_QUERY_TRIGGERS = [
    "what's on the menu", "whats on the menu", "what's planned", "whats planned",
    "what am i having", "what's my meal plan", "whats my meal plan", "my meal plan",
    "what's on my plan", "whats on my plan", "what's the plan", "whats the plan",
    "what am i making", "what's for dinner tonight", "whats for dinner tonight",
]
PLAN_SET_TRIGGERS = [
    "plan ", "schedule", "pencil in", "on the menu", "add to the menu",
]
# Personal events + the "what's coming up" look-ahead. Distinctive triggers so
# they don't collide with equipment's "i have a X" or pantry add.
CALENDAR_QUERY_TRIGGERS = [
    "coming up", "on my calendar", "anything going on", "what's going on",
    "whats going on", "what's happening", "whats happening",
    "sync my calendar", "sync calendar", "sync the calendar", "refresh my calendar",
    "what appointments", "any appointments", "my appointments",
    "what's on the calendar", "whats on the calendar", "my schedule",
]
# An action verb + the word "calendar" means WRITE (add), vs. a read query.
_CAL_ADD_VERBS = ("add ", "put ", "schedule", "create ", "book ", "set ")
EVENT_ADD_TRIGGERS = [
    "remind me", "add an event", "appointment", "have plans", "dinner plans",
    "i've got plans", "ive got plans", "i have a meeting", "i have a party",
    "i have a birthday", "add to my calendar", "dentist", "doctor's",
]
# WRITE to the real Google Calendar. Action-anchored so it beats the read query
# ("what's on my calendar") and the local event_add ("I have an appointment").
CALENDAR_ADD_TRIGGERS = [
    "to my calendar", "add an appointment", "create an event",
    "create a calendar event", "schedule an appointment",
    "add it to my calendar", "put it on my calendar", "add an event to my",
]
# Grocery-list management. Placed before add/remove so "add X to my grocery
# list" / "remove X from my grocery list" don't fall into pantry add/remove.
GROCERY_TRIGGERS = [
    "grocery list", "shopping list", "what do i need to buy", "need to buy",
]
# Dietary restrictions (set/list/remove). Before add/suggest so "I'm allergic to
# nuts" isn't a pantry add and "I'm vegetarian" isn't a suggestion.
DIETARY_TRIGGERS = [
    "allergic to", "allergy", "gluten free", "gluten-free", "dairy free",
    "dairy-free", "i'm vegetarian", "im vegetarian", "vegetarian", "vegan",
    "my restriction", "my restrictions", "dietary", "restriction", "i can eat",
    "not allergic",
]
# Rate a cooked recipe / query favorites. After cook + plan so "let's make X" and
# "I would like to make X" aren't caught; before suggest.
RATE_TRIGGERS = [
    "that was", "this was", "i love", "i loved", "i like", "i liked", "i enjoyed",
    "we loved", "i don't like", "i didn't like", "i dont like", "i hate",
    "rate", "don't suggest", "dont suggest", "never again", "delicious",
    "my favorite", "my favourite", "favorite recipe", "what do i like",
]
# Kitchen equipment (declare/list/remove). Specific appliance names + "I have a"
# phrasings; before add so "I've got a blender" isn't a pantry add. Bare common
# words (oven/grill/microwave) are omitted here to avoid shadowing cook.
# Flavor preferences (set/read/clear). The in-recipe "tone down the spice"
# adjustment is handled inside cooking (not here). Before rate.
FLAVOR_TRIGGERS = [
    "we like it", "we prefer", "we like our food", "we like our meals",
    "flavor preference", "flavour preference", "our flavor", "our flavour",
    "spice level", "spice tolerance", "keep it mild", "keep it spicy",
    "we like bold", "we like mild", "we don't like it too", "we dont like it too",
    "we like things", "our spice",
]
EQUIPMENT_TRIGGERS = [
    "equipment", "appliance", "blender", "food processor", "slow cooker",
    "crockpot", "crock pot", "air fryer", "pressure cooker", "instant pot",
    "waffle iron", "stand mixer",
    # trailing space so "i have a " matches "I have a blender" but not
    # "do I have any spinach" (the router pads the text with spaces).
    "i have a ", "i have an ", "i've got a ", "ive got a ",
    "i don't have a ", "i dont have a ",
]
LIST_TRIGGERS = [
    "what do i have", "what have i got", "what's in my", "whats in my",
    "what do i have left", "what's in stock", "whats in stock",
    "what's in the fridge", "whats in the fridge", "what's in the pantry",
    "whats in the pantry", "list my", "my inventory", "in my pantry",
    "what's in my pantry",
]
# Targeted "do we have X?" questions. These MUST be DB-grounded (inventory.check),
# never sent to the free LLM — otherwise the model invents inventory. "do i have"
# lives here (not LIST) so a specific-item question gets a yes/no, while the
# "what do i have" phrasings above still read back the whole pantry.
CHECK_TRIGGERS = [
    "do we have", "do i have", "do you have", "do we still have",
    "do i still have", "have we got", "have i got", "got any",
    "is there any", "are there any", "is there a", "are there",
]
COOK_TRIGGERS = [
    "let's make", "lets make", "let's cook", "lets cook", "walk me through",
    "guide me through", "how do i make", "how do you make", "how do i cook",
    "start the recipe", "start cooking", "help me make",
]
REMOVE_TRIGGERS = [
    "out of", "ran out", "run out", "used up", "used the last", "used all",
    "used the rest", "no more", "throw out", "threw out", "all gone",
    "remove ", "delete ",
]
ADD_TRIGGERS = [
    "bought", "grabbed", "picked up", "purchased", "just got", "stock up",
    " got ", "add ",
]


def classify(text: str) -> str:
    """Return 'volume', 'cook', 'recipe_query', 'suggest', 'list', 'check',
    'remove', 'add', or 'general'. Precedence:
    volume -> cook -> recipe_query -> suggest -> list -> check -> remove -> add
    -> general. (cook before recipe_query so "start the recipe for X" cooks while
    "do you have a recipe for X" queries the library;
    (cook before suggest so "let's make the omelette" starts a recipe while
    "what can I make" stays a browse; list before check so "what do I have"
    reads the whole pantry while "do I have milk" is a targeted lookup; check
    before add so "have we got X" / "got any X" isn't mistaken for a purchase;
    remove before add so "out of milk" isn't mistaken for a purchase.)"""
    t = " " + text.lower().strip() + " "
    if "volume" in t:
        return "volume"
    if any(k in t for k in COOK_TRIGGERS):
        return "cook"
    if any(k in t for k in RECIPE_QUERY_TRIGGERS):
        return "recipe_query"
    if any(k in t for k in NUTRITION_GOAL_TRIGGERS):
        return "nutrition_goal"
    if any(k in t for k in NUTRITION_LOG_TRIGGERS):
        return "nutrition_log"
    if any(k in t for k in NUTRITION_QUERY_TRIGGERS):
        return "nutrition_query"
    if any(k in t for k in PLAN_TRIGGERS):
        return "plan"
    if "calendar" in t and any(v in t for v in _CAL_ADD_VERBS):
        return "calendar_add"                # "put/add/schedule ... calendar" -> write
    if any(k in t for k in PLAN_QUERY_TRIGGERS):
        return "plan_query"
    if any(k in t for k in PLAN_SET_TRIGGERS):
        return "plan_set"
    if any(k in t for k in CALENDAR_ADD_TRIGGERS):
        return "calendar_add"
    if any(k in t for k in CALENDAR_QUERY_TRIGGERS):
        return "calendar_query"
    if any(k in t for k in EVENT_ADD_TRIGGERS):
        return "event_add"
    if any(k in t for k in GROCERY_TRIGGERS):
        return "grocery"
    if any(k in t for k in DIETARY_TRIGGERS):
        return "dietary"
    if any(k in t for k in FLAVOR_TRIGGERS):
        return "flavor"
    if any(k in t for k in RATE_TRIGGERS):
        return "rate"
    if any(k in t for k in EQUIPMENT_TRIGGERS):
        return "equipment"
    if any(k in t for k in EXPIRING_TRIGGERS):
        return "expiring"
    if any(k in t for k in QUICK_TRIGGERS):
        return "quick"
    if any(k in t for k in SEASONAL_TRIGGERS):
        return "seasonal"
    if any(k in t for k in BUDGET_TRIGGERS):
        return "budget"
    if any(k in t for k in SUGGEST_TRIGGERS):
        return "suggest"
    if any(k in t for k in LIST_TRIGGERS):
        return "list"
    if any(k in t for k in CHECK_TRIGGERS):
        return "check"
    if any(k in t for k in REMOVE_TRIGGERS):
        return "remove"
    if any(k in t for k in ADD_TRIGGERS):
        return "add"
    return "general"
