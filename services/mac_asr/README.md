# Mac ASR Service

One job: **transcribe audio**. HTTP API that accepts an audio file and returns the transcription using macOS Speech framework.

## Endpoint

- **POST /v1/audio/transcriptions** — `file` (required), optional `language` (e.g. `es-ES`).  
  If `language` is omitted, the system uses the default macOS locale.  
  Returns `{ "text", "locale" }` (locale may be empty when using the default).
- **GET /health** — readiness and locale.

## Run

From `services/mac_asr`:

```bash
uv sync
uv run mac-asr-service
```

Config: copy `.env.example` to `.env` and adjust. Keys: `MAC_ASR_HOST`, `MAC_ASR_PORT`, `MAC_ASR_LOCALE`, `MAC_ASR_TRANSCRIPTION_TIMEOUT_S`, `MAC_ASR_PROMPT_PERMISSION`, `MAC_ASR_LOG_LEVEL`.
Leave `MAC_ASR_LOCALE` empty to use the default macOS locale.

## Permissions

macOS Speech Recognition must be allowed (e.g. **System Settings → Privacy & Security → Speech Recognition** for Terminal/Cursor).
