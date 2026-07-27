"""Manual test (needs mic): prints when the wake word is detected."""
from remy.wake import WakeListener

print("Loading wake model...")
w = WakeListener()
print("Say the wake word ('hey jarvis' for the prototype model)...")
w.wait()
print("WAKE WORD DETECTED!")
