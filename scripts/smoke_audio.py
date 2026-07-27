"""Manual test (needs mic + speaker): records until you stop talking, plays it back."""
from john_whisk import audio

print("Speak after this line prints; stop when done...")
path = audio.record_until_silence()
if path:
    print("Captured:", path, "-> playing back")
    audio.play_wav(path)
else:
    print("No speech detected.")
