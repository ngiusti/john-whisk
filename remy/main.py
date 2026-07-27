import logging
from remy import config, wake, audio, stt, llm, tts

logging.basicConfig(
    filename=config.LOG_FILE, level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("remy")


def handle_turn(listener):
    listener.wait()                      # blocks until wake word
    log.info("wake word detected")
    print("[wake detected -> asking]", flush=True)
    audio.chime()                        # audible beep: Remy heard the wake word, ask now
    wav = audio.record_until_silence()
    if not wav:
        tts.speak("I didn't catch that.")
        return
    text = stt.transcribe(wav)
    log.info("heard: %s", text)
    print("heard:", text, flush=True)
    if not text.strip():
        tts.speak("I didn't catch that.")
        return
    reply = llm.ask(text)
    log.info("reply: %s", reply)
    print("reply:", reply, flush=True)
    if not reply.strip():
        tts.speak("Sorry, my brain hiccupped. Try again.")
        return
    tts.speak(reply)


def main():
    log.info("Remy starting up")
    listener = wake.WakeListener()
    tts.speak("Remy is ready.")          # spoken cue: you'll hear this when it's listening
    print("Remy is listening. Say the wake word.", flush=True)
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
