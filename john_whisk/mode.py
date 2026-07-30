"""A lightweight conversational 'mode' so the user can steer ambiguous commands
into a domain. "Let's look into the calendar" -> calendar mode, where fuzzy
commands ("dentist Friday at 4pm", "anything Tuesday?") are read as calendar
actions until they exit or clearly switch domains. Off by default."""
_state = {"mode": None}

CALENDAR_SET = (
    "look into the calendar", "look into my calendar", "into my calendar",
    "calendar mode", "switch to calendar", "go to calendar", "go into the calendar",
    "open my calendar", "open the calendar", "work on my calendar",
    "manage my calendar", "let's do calendar", "lets do calendar",
    "let's look at the calendar", "lets look at the calendar", "look at my calendar",
)
EXIT = (
    "never mind", "nevermind", "back to normal", "back to the kitchen",
    "that's all", "thats all", "all done", "go back", "exit calendar",
    "leave calendar", "we're done", "were done", "done with the calendar",
)


def get():
    return _state["mode"]


def set(m):
    _state["mode"] = m


def clear():
    _state["mode"] = None


def detect_set(text):
    """Return a mode name if the utterance asks to enter one, else None."""
    t = " " + (text or "").lower().strip() + " "
    if any(p in t for p in CALENDAR_SET):
        return "calendar"
    return None


def is_exit(text):
    t = " " + (text or "").lower().strip() + " "
    return any(p in t for p in EXIT)
