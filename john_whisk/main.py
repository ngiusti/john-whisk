import logging
from john_whisk import config, wake, audio, stt, llm, tts, router, inventory, db, volume

logging.basicConfig(
    filename=config.LOG_FILE, level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("john_whisk")


def handle_turn(listener):
    listener.wait()                      # blocks until wake word
    log.info("wake word detected")
    print("[wake detected -> asking]", flush=True)
    audio.chime()                        # audible beep: John Whisk heard the wake word, ask now
    wav = audio.record_until_silence()
    if not wav:
        tts.speak("I didn't catch that.")
        return
    tts.speak("Let me see.")             # instant feedback: heard you, working on it
    text = stt.transcribe(wav)
    log.info("heard: %s", text)
    print("heard:", text, flush=True)
    if not text.strip():
        tts.speak("I didn't catch that.")
        return
    intent = router.classify(text)
    log.info("intent: %s", intent)
    if intent == "volume":
        reply = volume.set_from_text(text)
    elif intent == "add":
        reply = inventory.add_from_text(text)
    elif intent == "suggest":
        reply = inventory.suggest(text)
    elif intent == "list":
        reply = inventory.list_stock()
    elif intent == "remove":
        reply = inventory.remove_from_text(text)
    else:
        reply = llm.ask(text)
    log.info("reply: %s", reply)
    print("reply:", reply, flush=True)
    if not reply.strip():
        tts.speak("Sorry, my brain hiccupped. Try again.")
        return
    tts.speak(reply)


def main():
    log.info("John Whisk starting up")
    db.init_db()
    listener = wake.WakeListener()
    tts.speak("John Whisk is ready.")    # spoken cue: you'll hear this when it's listening
    print("John Whisk is listening. Say the wake word.", flush=True)
    while True:
        try:
            handle_turn(listener)
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
