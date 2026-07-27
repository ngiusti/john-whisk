from john_whisk import config


def test_core_constants_present():
    assert config.SAMPLE_RATE == 16000
    assert config.MIC_DEVICE.startswith("plughw:")
    assert config.SPEAKER_DEVICE.startswith("plughw:")
    assert config.NUM_CTX == 2048          # required or the 3B OOMs
    assert "John Whisk" in config.SYSTEM_PROMPT
    assert config.WAKE_THRESHOLD > 0
