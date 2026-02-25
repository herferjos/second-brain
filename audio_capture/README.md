# Audio Capture (Host Mic -> LifeLog Collector)

Captures microphone audio with VAD and sends `.wav` chunks to the LifeLog collector at `/audio`.

This pipeline is now disabled by default via `AUDIO_CAPTURE_ENABLED=0` to avoid accidentally re-capturing system playback. Prefer the browser extension tab audio recorder when you only want browser output.

## Setup

1. Install dependencies:
   ```bash
   pip install -r audio_capture/requirements.txt
   ```

2. Create env file:
   ```bash
   cp audio_capture/.env.example audio_capture/.env
   ```

3. Start the collector (in a separate terminal):
   ```bash
   pip install -r collector/requirements.txt
   python -m uvicorn collector.main:app --host 127.0.0.1 --port 8787
   ```

4. Run audio capture:
   ```bash
   set -a && source audio_capture/.env && set +a
   python audio_capture/main.py
   ```

## Notes

- If the collector is temporarily unavailable, chunks remain in `audio_capture/spool` and are retried.
- Use `AUDIO_CAPTURE_INPUT_DEVICE` if the default mic is not the right one.
- `AUDIO_CAPTURE_MIN_RMS` filters near-silent chunks before upload. Increase it to drop more noise.
- Env vars support `AUDIO_CAPTURE_*` (preferred) or legacy `AUDIO_BRIDGE_*`.
