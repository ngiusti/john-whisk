import logging
from john_whisk import config, wake, audio, stt, llm, tts, router, inventory, db, volume, cooking, recipes, grocery, restrictions

logging.basicConfig(
    filename=config.LOG_FILE, level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("john_whisk")


def process_utterance(text, kitchen):
    """Route one transcribed utterance, mutating `kitchen` (the recipe queue).
    Returns the spoken reply."""
    if cooking.is_recipes_query(text):
        return kitchen.summary()             # "what am I making" — works anytime
    if kitchen.active:
        return kitchen.navigate(text)        # in a recipe: nav / enqueue / cancel-all
    intent = router.classify(text)
    log.info("intent: %s", intent)
    if intent == "cook":
        return kitchen.begin(cooking.dish_from_text(text))
    if intent == "recipe_query":
        return recipes.answer_query(text)
    if intent == "plan":
        return grocery.plan_meal(cooking.dish_from_text(text))
    if intent == "grocery":
        return grocery.handle(text)
    if intent == "dietary":
        return restrictions.handle(text)
    if intent == "volume":
        return volume.set_from_text(text)
    if intent == "add":
        return inventory.add_from_text(text)
    if intent == "suggest":
        return inventory.suggest(text)
    if intent == "list":
        return inventory.list_stock()
    if intent == "check":
        return inventory.check(text)
    if intent == "remove":
        return inventory.remove_from_text(text)
    # general fallback: grounded with the real pantry so it can't invent inventory
    return inventory.ask_general(text)


def _listen(listener, kitchen, hands_free):
    """Capture one utterance. Hands-free (opt-in, mid-recipe) listens without the
    wake word and gives up after COOK_LISTEN_MS of silence. Otherwise it waits
    for the wake word; while a recipe is active it finalizes on the shorter
    COOK_SILENCE_MS so "next"/"back" turn around fast. Returns a WAV path or None."""
    if hands_free:
        return audio.record_until_silence(
            start_timeout_ms=config.COOK_LISTEN_MS,
            max_utterance_ms=config.COOK_MAX_UTTERANCE_MS,
            silence_ms=config.COOK_SILENCE_MS,
        )
    listener.wait()                      # blocks until wake word
    log.info("wake word detected")
    print("[wake detected -> asking]", flush=True)
    audio.chime()                        # audible beep: heard the wake word, ask now
    if kitchen.active:
        # in a recipe: short commands, finalize quickly (keep the full cap in case
        # it's a longer free-form question)
        return audio.record_until_silence(silence_ms=config.COOK_SILENCE_MS)
    return audio.record_until_silence()


def main():
    log.info("John Whisk starting up")
    db.init_db()
    listener = wake.WakeListener()
    tts.speak("John Whisk is ready.")    # spoken cue: you'll hear this when it's listening
    print("John Whisk is listening. Say the wake word.", flush=True)
    kitchen = cooking.Kitchen()           # active recipe + queue, empty when not cooking
    hands_free = False                    # skip the wake word while cooking
    while True:
        try:
            wav = _listen(listener, kitchen, hands_free)
            if not wav:
                if hands_free:
                    # silence mid-recipe: re-arm the wake word, keep the recipe
                    log.info("hands-free timeout; recipe paused, waiting for wake word")
                    hands_free = False
                else:
                    tts.speak("I didn't catch that.")
                continue
            if not kitchen.active and not hands_free:
                tts.speak("Let me see.")  # cue only for non-recipe turns (may be slow);
                                          # in-recipe nav is instant, so stay quiet
            text = stt.transcribe(wav)
            log.info("heard: %s", text)
            print("heard:", text, flush=True)
            if not text.strip():
                if not hands_free:
                    tts.speak("I didn't catch that.")
                continue
            # noise guard while cooking hands-free: ignore anything that isn't a
            # nav command, a queue action, or the "what am I making" query
            if hands_free and cooking.classify_nav(text) == "unknown" \
                    and not cooking._is_cook_request(text) \
                    and not cooking._is_cancel_all(text) \
                    and not cooking.is_recipes_query(text):
                log.info("hands-free: ignoring non-command: %s", text)
                continue
            reply = process_utterance(text, kitchen)
            log.info("reply: %s", reply)
            print("reply:", reply, flush=True)
            if reply.strip():
                tts.speak(reply)
            elif not hands_free:
                tts.speak("Sorry, my brain hiccupped. Try again.")
            # stay hands-free while cooking only if the opt-in toggle is on
            hands_free = kitchen.active and config.HANDS_FREE_COOKING
        except KeyboardInterrupt:
            print("\nShutting down.")
            break
        except Exception:
            log.exception("turn failed")
            try:
                tts.speak("Something went wrong, but I'm still here.")
            except Exception:
                log.exception("could not speak error")


if __name__ == "__main__":
    main()
