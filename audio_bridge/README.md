# Audio Bridge (Host Mic -> Docker API)

This process runs on your Mac host, captures microphone audio with VAD, and sends `.wav` chunks to the Docker API endpoint `/audio`.

## Setup

1. Install dependencies:
   ```bash
   ./.venv/bin/pip install -r audio_bridge/requirements.txt
   ```
2. Create bridge env file:
   ```bash
   cp audio_bridge/.env.example audio_bridge/.env
   ```
3. Start Docker API:
   ```bash
   docker compose up -d --build
   ```
4. Run bridge:
   ```bash
   set -a && source audio_bridge/.env && set +a
   ./.venv/bin/python audio_bridge/main.py
   ```

## Notes

- The Docker API no longer captures mic audio directly; this bridge does it from host.
- If API is temporarily unavailable, chunks remain in `audio_bridge/spool` and are retried.
- Use `AUDIO_BRIDGE_INPUT_DEVICE` if default mic is not the right one.
- `AUDIO_BRIDGE_MIN_RMS` filters near-silent chunks before upload. Increase it to drop more noise.
