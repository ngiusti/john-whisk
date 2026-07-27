import os
import time
import subprocess
import wave
import contextlib
import numpy as np
import webrtcvad
from remy import config

_CHIME_PATH = "/tmp/remy_chime.wav"


def _open_mic_stream(frame_bytes: int):
    """Open arecord and confirm it is STABLY streaming. Retries if the ALSA
    device is momentarily busy or resets right after opening (release lag from
    the wake listener). Returns a live Popen (priming frames consumed) or None."""
    time.sleep(0.3)                         # let the previous mic user's ALSA release settle
    for _ in range(20):                     # up to ~5s of retries
        proc = subprocess.Popen(
            ["arecord", "-D", config.MIC_DEVICE, "-f", "S16_LE",
             "-r", str(config.SAMPLE_RATE), "-c", "1", "-t", "raw", "-q"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        # require several consecutive full frames — one isn't enough to prove
        # the stream survived the device reset.
        stable = all(len(proc.stdout.read(frame_bytes)) == frame_bytes for _ in range(5))
        if stable:
            return proc
        proc.terminate()
        proc.wait()
        time.sleep(0.2)
    return None


def play_wav(path: str) -> None:
    """Play a WAV file through the configured speaker."""
    subprocess.run(["aplay", "-D", config.SPEAKER_DEVICE, path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _ensure_chime() -> str:
    """Create a short beep WAV once (880Hz, ~0.18s, faded to avoid clicks)."""
    if not os.path.exists(_CHIME_PATH):
        sr = config.SAMPLE_RATE
        n = int(sr * 0.18)
        t = np.linspace(0, 0.18, n, False)
        tone = 0.3 * np.sin(2 * np.pi * 880 * t)
        fade = int(sr * 0.01)
        tone[:fade] *= np.linspace(0, 1, fade)
        tone[-fade:] *= np.linspace(1, 0, fade)
        _write_wav(_CHIME_PATH, (tone * 32767).astype(np.int16).tobytes())
    return _CHIME_PATH


def chime() -> None:
    """Play a short beep — the 'I heard the wake word, ask now' cue."""
    play_wav(_ensure_chime())


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

    proc = _open_mic_stream(frame_bytes)
    if proc is None:
        return None                          # mic never became available
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
