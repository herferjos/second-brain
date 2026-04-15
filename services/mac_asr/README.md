# Mac Transcription Service

One job: **transcribe audio**. HTTP API that accepts an audio file and returns a LiteLLM/OpenAI-compatible transcription payload using the native macOS Speech framework. The service is shaped like the OpenAI Whisper API so Exocort can treat it as a Whisper-style ASR backend.

## Endpoint

- **POST /v1/audio/transcriptions**
  Expected request format: `multipart/form-data`
  Accepted fields: `file` (required), `model`, `language`, `prompt`, `response_format`, `temperature`
  If `language` is omitted, the service resolves it from `locale` in `config.yaml` and can auto-detect when configured.
  Expected JSON response format:

```json
{
  "text": "hola mundo",
  "task": "transcribe",
  "language": "es-ES",
  "duration": null
}
```

  If no speech is detected, or the request is discarded by language detection, it returns the same JSON shape with `text` set to an empty string.
  If another `response_format` is sent, the service returns HTTP `400`.
- **GET /health** — readiness and locale.

This is the transcription format Exocort expects when it sends audio through LiteLLM-compatible endpoints.

## Run

From `services/mac_asr`:

```bash
uv sync
uv run mac-asr-service
```

Config: use `example.yaml` as the base for `config.yaml`. Keys: `host`, `port`, `reload`, `locale`, `default_locale`, `transcription_timeout_s`, `prompt_permission`, `log_level`, `detect_model`, `detect_device`, `detect_compute_type`, `detect_discard_min_prob`, `detect_default_min_prob`.
Set `locale: auto` to enable language detection by default, or use a fixed locale like `es-ES` to force transcription in that locale.
`default_locale` is used whenever detection is enabled but its confidence is below 70%; it defaults to `es`.
The service maps bare language codes like `es` to a supported macOS locale before transcription, so you can use either `es` or `es-ES`.
`detect_discard_min_prob` defaults to `0.5`; below that the audio is discarded and the service returns an empty transcription payload.
`detect_default_min_prob` defaults to `0.7`; between the two thresholds the service falls back to `default_locale`.

Language detection
------------------

If `locale: auto` and the request omits `language` (or uses `auto`),
the service uses `faster-whisper` to detect the language and maps it to a supported
macOS locale before transcription. If the detected probability is below 50%, it discards
the audio and returns an empty transcription payload. Between 50% and 70%, it falls back to `default_locale`
instead of trusting the prediction. The detection
model defaults to `tiny` but can be overridden via `detect_model`.
`faster-whisper` bundles the FFmpeg runtime it needs, so you do not have to install
system `ffmpeg`, but the model weights add size.

## Permissions

macOS Speech Recognition must be allowed (e.g. **System Settings → Privacy & Security → Speech Recognition** for Terminal/Cursor).
