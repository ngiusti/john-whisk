# Custom "Hey John Whisk" Wake Word — Design

Status: approved 2026-07-27. Revives the deferred custom wake word (was blocked
by the broken openWakeWord training Colab).

## Goal

Replace the built-in "hey jarvis" wake word with a custom "Hey John Whisk"
model, keeping the current openWakeWord onnx runtime on the Pi. Fully local: the
model is trained on the Windows dev PC and only the resulting .onnx ships to the
Pi. No engine change, no cloud service.

## Validation already done (why this is feasible now)

openWakeWord's `train.py` exports onnx via **`torch.onnx.export`** directly
(functions `export_to_onnx`, `export_model`) — pure torch, no TensorFlow, no
`onnx_tf`. The broken dependency chain (`onnx_tf` + `tensorflow`) is used ONLY by
`convert_onnx_to_tflite`, i.e. the tflite output we don't need (the Pi runs the
onnx backend). The prior failure was the automatic script crashing at the tflite
step AFTER the onnx export. Fix: train, export onnx, and SKIP the tflite
conversion. The exported onnx uses the same `torch.onnx.export` + opset as the
shipped `hey_jarvis` model that already runs on the Pi, so it loads identically.

## Environment (measured 2026-07-27)

- **Training host:** this Windows PC — RTX 5070 (12GB, Blackwell), 48GB RAM,
  83GB free, git present. System Python is 3.14.5 (too new for the ML stack).
- **Pi:** inference only — Python 3.13, `onnxruntime` 1.28.0, openWakeWord on the
  onnx backend, no torch/tf (correct). `models/` is empty.

## Architecture / steps

### 1. Isolated training environment (Windows)
A dedicated **Python 3.11** venv, separate from system 3.14 (via `uv` or a 3.11
install). Install: `torch` (CUDA build for the 5070 if it installs cleanly, else
CPU wheel — the model is small so CPU is acceptable), `openwakeword` with
training extras, `piper-sample-generator`, and training dependencies. Kept under
a scratch dir on Windows (not committed; not in the Pi repo).

### 2. Synthetic training data
`piper-sample-generator` synthesizes many "Hey John Whisk" utterances across
varied voices, speeds, and pitches (positives). openWakeWord's negative /
background feature sets + room-impulse responses provide negatives and
augmentation (a few GB of downloads). No human recording required.

### 3. Train + export onnx ONLY
Run openWakeWord training (GPU if available, CPU fallback). On completion call
`export_model` / `export_to_onnx` to write `Hey_John_Whisk.onnx`, and DO NOT call
`convert_onnx_to_tflite` (the broken step). Sanity-load the onnx locally with
onnxruntime to confirm it opens and has the expected input/output shape.

### 4. Deploy to the Pi
`scp Hey_John_Whisk.onnx` -> `~/john-whisk/models/`. Update `john_whisk/config.py`:
`WAKE_MODEL` = absolute path to the onnx; keep `WAKE_INFERENCE_FRAMEWORK = "onnx"`.
`wake.WakeListener` already passes `WAKE_MODEL` to `openwakeword.Model`, so no code
change beyond config. Commit on a `wake-word` branch (the .onnx is git-ignored via
`models/*.onnx`; document how to regenerate it).

### 5. Live validation + tuning (the real success test)
On the Pi: confirm the model loads, then speak "Hey John Whisk" and confirm the
chime fires. Tune `WAKE_THRESHOLD` (default 0.5): raise it if it false-fires on
background speech, lower it if it misses. Confirm it does NOT trigger on "hey
jarvis" or ambient talk. Restart the service and verify across a normal turn
(wake -> ask -> answer). If quality is poor, a second training pass with more
positive samples / more steps.

## Error handling / fallbacks

- Blackwell CUDA torch won't install cleanly -> CPU training (small model, still
  feasible; slower but fine).
- Python 3.11 unavailable -> fetch via `uv python install 3.11`.
- Poor detection or false fires -> threshold tuning first, then retrain with more
  data / steps. The old `hey_jarvis` config is one line to restore if needed.
- All training artifacts stay on Windows; only the vetted .onnx reaches the Pi,
  so a bad run never touches the running assistant until deploy.

## Testing

- Local: after export, load the onnx in onnxruntime and assert it initializes
  with the expected feature input shape (cheap, deterministic).
- On-device: manual live validation (wake / no-false-fire / full turn), reported
  with what was observed and the final threshold. Wake detection is inherently
  hardware/audio-coupled, so this step is manual, not unit-tested.

## Out of scope

- Retraining automation / CI.
- Multiple wake phrases or per-user wake tuning.
- Changing the wake ENGINE (staying on openWakeWord onnx).
- The Ollama version update (separate ops task, done alongside).
