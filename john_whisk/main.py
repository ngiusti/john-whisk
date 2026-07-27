import logging
from john_whisk import config, wake, audio, stt, llm, tts, router, inventory, db, volume, cooking

logging.basicConfig(
    filename=config.LOG_FILE, level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("john_whisk")


def process_utterance(text, session):
    """Route one transcribed utterance. Returns (spoken reply, session) with a
    uniform tuple order; session is the (possibly new/updated/None) recipe."""
    if session is not None:
        # mid-recipe: interpret the utterance as a navigation command
        return cooking.navigate(session, text)
    intent = router.classify(text)
    log.info("intent: %s", intent)
    if intent == "cook":
        session, reply = cooking.start(cooking.dish_from_text(text))
        return reply, session
    if intent == "volume":
        return volume.set_from_text(text), session
    if intent == "add":
        return inventory.add_from_text(text), session
    if intent == "suggest":
        return inventory.suggest(text), session
    if intent == "list":
        return inventory.list_stock(), session
    if intent == "check":
        return inventory.check(text), session
    if intent == "remove":
        return inventory.remove_from_text(text), session
    # general fallback: grounded with the real pantry so it can't invent inventory
    return inventory.ask_general(text), session


def _listen(listener, session, hands_free):
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
    if session is not None:
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
    session = None                        # active CookingSession, or None when not cooking
    hands_free = False                    # skip the wake word while cooking
    while True:
        try:
            wav = _listen(listener, session, hands_free)
            if not wav:
                if hands_free:
                    # silence mid-recipe: re-arm the wake word, keep the recipe
                    log.info("hands-free timeout; recipe paused, waiting for wake word")
                    hands_free = False
                else:
                    tts.speak("I didn't catch that.")
                continue
            if session is None and not hands_free:
                tts.speak("Let me see.")  # cue only for non-recipe turns (may be slow);
                                          # in-recipe nav is instant, so stay quiet
            text = stt.transcribe(wav)
            log.info("heard: %s", text)
            print("heard:", text, flush=True)
            if not text.strip():
                if not hands_free:
                    tts.speak("I didn't catch that.")
                continue
            if hands_free and cooking.classify_nav(text) == "unknown":
                # noise / off-command speech while cooking: ignore, keep listening
                log.info("hands-free: ignoring non-command: %s", text)
                continue
            reply, session = process_utterance(text, session)
            log.info("reply: %s", reply)
            print("reply:", reply, flush=True)
            if reply.strip():
                tts.speak(reply)
            elif not hands_free:
                tts.speak("Sorry, my brain hiccupped. Try again.")
            # stay hands-free while cooking only if the opt-in toggle is on
            hands_free = session is not None and config.HANDS_FREE_COOKING
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
