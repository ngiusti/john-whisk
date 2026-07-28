"""Deployment invariant: the shipped config must select the trained custom wake
model, not the built-in 'hey_jarvis'. Guards against a stale-copy scp silently
reverting WAKE_MODEL (which is exactly what happened once)."""
from john_whisk import config


def test_wake_model_is_custom_hey_john_whisk():
    assert config.WAKE_MODEL.endswith("hey_john_whisk.onnx"), (
        f"WAKE_MODEL should point at the custom model, got {config.WAKE_MODEL!r}")
