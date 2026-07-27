"""Diagnostic: record ~10s, print the peak wake-word score seen. Say the phrase a few times."""
import subprocess
import numpy as np
from openwakeword.model import Model
from remy import config

print("loading model...", flush=True)
m = Model(wakeword_models=[config.WAKE_MODEL],
          inference_framework=config.WAKE_INFERENCE_FRAMEWORK)
proc = subprocess.Popen(
    ["arecord", "-D", config.MIC_DEVICE, "-f", "S16_LE",
     "-r", str(config.SAMPLE_RATE), "-c", "1", "-t", "raw", "-q"],
    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
)
print("LISTENING ~10s — say 'hey jarvis' a few times now", flush=True)
peak = 0.0
chunks = int(10 * config.SAMPLE_RATE / 1280)
for _ in range(chunks):
    data = proc.stdout.read(1280 * 2)
    if len(data) < 1280 * 2:
        break
    audio = np.frombuffer(data, dtype=np.int16)
    score = m.predict(audio).get(config.WAKE_MODEL, 0.0)
    if score > peak:
        peak = score
proc.terminate()
proc.wait()
print(f"PEAK {config.WAKE_MODEL} score = {peak:.3f}  (threshold is {config.WAKE_THRESHOLD})", flush=True)
