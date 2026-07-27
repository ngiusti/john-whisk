import os
import time
import subprocess
import wave
import contextlib
import numpy as np
import webrtcvad
from john_whisk import config

_CHIME_PATH = "/tmp/john_whisk_chime.wav"


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


def _open_mic_stream(frame_bytes: int):
    """Open arecord and confirm it is STABLY streaming. Retries if the ALSA
    device is momentarily busy or resets right after opening (release lag from
    the wake listener). Returns (live Popen, primed_bytes) or (None, b"").
    The primed frames are KEPT (returned) so the start of speech isn't clipped."""
    time.sleep(0.15)                        # brief settle (the wake arecord already closed during the chime)
    for _ in range(20):                     # up to ~4s of retries
        proc = subprocess.Popen(
            ["arecord", "-D", config.MIC_DEVICE, "-f", "S16_LE",
             "-r", str(config.SAMPLE_RATE), "-c", "1", "-t", "raw", "-q"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        # read a few frames to prove the stream survived the device reset,
        # but keep them (don't discard) so no audio is lost.
        primed = bytearray()
        stable = True
        for _ in range(4):
            f = proc.stdout.read(frame_bytes)
            if len(f) != frame_bytes:
                stable = False
                break
            primed += f
        if stable:
            return proc, bytes(primed)
        proc.terminate()
        proc.wait()
        time.sleep(0.2)
    return None, b""


def record_until_silence(out_path: str = None, start_timeout_ms: int = None,
                         max_utterance_ms: int = None, silence_ms: int = None):
    """Record from the mic until ~silence_ms of trailing silence after speech.
    Returns out_path if speech was captured, else None.
    Streams raw PCM from arecord and gates with webrtcvad (30ms frames).
    If start_timeout_ms is set and no speech has BEGUN within that window, give
    up early and return None (used for hands-free listening between recipe
    steps, so a silent pause doesn't hold the mic for the full utterance cap).
    max_utterance_ms and silence_ms override the config defaults — hands-free
    passes shorter values so short commands finalize fast and a noise-triggered
    clip caps quickly instead of running to the full wake-gated cap."""
    out_path = out_path or config.IN_WAV
    vad = webrtcvad.Vad(config.VAD_AGGRESSIVENESS)
    frame_ms = 30
    frame_bytes = int(config.SAMPLE_RATE * frame_ms / 1000) * 2   # 960 bytes
    max_frames = (max_utterance_ms or config.MAX_UTTERANCE_MS) // frame_ms
    silence_frames_needed = (silence_ms or config.SILENCE_MS) // frame_ms
    min_speech_frames = config.MIN_SPEECH_MS // frame_ms
    start_timeout_frames = (start_timeout_ms // frame_ms) if start_timeout_ms else None

    proc, primed = _open_mic_stream(frame_bytes)
    if proc is None:
        return None                          # mic never became available
    collected = bytearray()
    voiced_frames = 0
    trailing_silence = 0
    started = False
    total = 0

    def _handle(frame):
        """Run one 30ms frame through VAD. Returns True when the utterance is done."""
        nonlocal voiced_frames, trailing_silence, started
        if vad.is_speech(frame, config.SAMPLE_RATE):
            started = True
            voiced_frames += 1
            trailing_silence = 0
            collected.extend(frame)
        elif started:
            trailing_silence += 1
            collected.extend(frame)
        return started and trailing_silence >= silence_frames_needed

    try:
        stop = False
        # process the kept priming frames first, then the live stream
        for i in range(0, len(primed) - frame_bytes + 1, frame_bytes):
            total += 1
            if _handle(primed[i:i + frame_bytes]):
                stop = True
                break
        while not stop and total < max_frames:
            # hands-free: bail if no one has started speaking within the window
            if start_timeout_frames is not None and not started and total >= start_timeout_frames:
                break
            frame = proc.stdout.read(frame_bytes)
            if len(frame) < frame_bytes:
                break
            total += 1
            if _handle(frame):
                break
    finally:
        proc.terminate()
        proc.wait()

    if not started or voiced_frames < min_speech_frames:
        return None
    _write_wav(out_path, bytes(collected))
    return out_path
