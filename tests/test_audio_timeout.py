from john_whisk import audio, config


class _SilentProc:
    """Fake arecord stream that only ever yields digital silence (zeros),
    which webrtcvad classifies as non-speech."""

    class _Out:
        def read(self, n):
            return b"\x00" * n

    def __init__(self):
        self.stdout = self._Out()

    def terminate(self):
        pass

    def wait(self):
        pass


def test_start_timeout_returns_none_when_no_speech(monkeypatch):
    # No speech ever begins -> record_until_silence must bail at the start
    # timeout and return None, not wait out the full MAX_UTTERANCE cap.
    monkeypatch.setattr(audio, "_open_mic_stream", lambda fb: (_SilentProc(), b""))
    assert audio.record_until_silence(start_timeout_ms=300) is None


def test_no_start_timeout_runs_to_cap_on_silence(monkeypatch):
    # Without a start timeout, pure silence still returns None (nothing captured),
    # confirming the new parameter is the only thing that shortens the wait.
    monkeypatch.setattr(audio, "_open_mic_stream", lambda fb: (_SilentProc(), b""))
    monkeypatch.setattr(config, "MAX_UTTERANCE_MS", 300)   # keep the test fast
    assert audio.record_until_silence() is None
