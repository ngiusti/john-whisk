import subprocess
import numpy as np
from openwakeword.model import Model
from john_whisk import config


class WakeListener:
    """Blocks until the wake word is heard on the mic (openWakeWord)."""

    CHUNK_SAMPLES = 1280          # openWakeWord expects 80ms @ 16kHz
    CHUNK_BYTES = CHUNK_SAMPLES * 2

    def __init__(self):
        self.model = Model(
            wakeword_models=[config.WAKE_MODEL],
            inference_framework=config.WAKE_INFERENCE_FRAMEWORK,
        )
        self.threshold = config.WAKE_THRESHOLD

    def wait(self) -> None:
        """Return once the wake word crosses the detection threshold."""
        self.model.reset()
        proc = subprocess.Popen(
            ["arecord", "-D", config.MIC_DEVICE, "-f", "S16_LE",
             "-r", str(config.SAMPLE_RATE), "-c", "1", "-t", "raw", "-q"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        try:
            while True:
                data = proc.stdout.read(self.CHUNK_BYTES)
                if len(data) < self.CHUNK_BYTES:
                    break
                audio = np.frombuffer(data, dtype=np.int16)
                scores = self.model.predict(audio)
                if max(scores.values()) >= self.threshold:
                    return
        finally:
            proc.terminate()
            proc.wait()
