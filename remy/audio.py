import subprocess
import wave
import contextlib
import webrtcvad
from remy import config


def play_wav(path: str) -> None:
    """Play a WAV file through the configured speaker."""
    subprocess.run(["aplay", "-D", config.SPEAKER_DEVICE, path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _write_wav(path, pcm_bytes):
    with contextlib.closing(wave.open(path, "wb")) as w:
        w.setnchannels(1)
        w.setsampwidth(2)          # S16_LE
        w.setframerate(config.SAMPLE_RATE)
        w.writeframes(pcm_bytes)


def record_until_silence(out_path: str = None):
    """Record from the mic until ~SILENCE_MS of trailing silence after speech.
    Returns out_path if speech was captured, else None.
    Streams raw PCM from arecord and gates with webrtcvad (30ms frames)."""
    out_path = out_path or config.IN_WAV
    vad = webrtcvad.Vad(config.VAD_AGGRESSIVENESS)
    frame_ms = 30
    frame_bytes = int(config.SAMPLE_RATE * frame_ms / 1000) * 2   # 960 bytes
    max_frames = config.MAX_UTTERANCE_MS // frame_ms
    silence_frames_needed = config.SILENCE_MS // frame_ms
    min_speech_frames = config.MIN_SPEECH_MS // frame_ms

    proc = subprocess.Popen(
        ["arecord", "-D", config.MIC_DEVICE, "-f", "S16_LE",
         "-r", str(config.SAMPLE_RATE), "-c", "1", "-t", "raw", "-q"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    collected = bytearray()
    voiced_frames = 0
    trailing_silence = 0
    started = False
    total = 0
    try:
        while total < max_frames:
            frame = proc.stdout.read(frame_bytes)
            if len(frame) < frame_bytes:
                break
            total += 1
            is_speech = vad.is_speech(frame, config.SAMPLE_RATE)
            if is_speech:
                started = True
                voiced_frames += 1
                trailing_silence = 0
                collected.extend(frame)
            elif started:
                trailing_silence += 1
                collected.extend(frame)
                if trailing_silence >= silence_frames_needed:
                    break
    finally:
        proc.terminate()
        proc.wait()

    if not started or voiced_frames < min_speech_frames:
        return None
    _write_wav(out_path, bytes(collected))
    return out_path
