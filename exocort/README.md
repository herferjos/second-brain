# Exocort capturers and processors

Minimal runner that boots the enabled capture and processing services defined in the YAML config.

1. Install dependencies with `uv sync` from the `exocort` directory.
2. Adjust the YAML file to configure `capturer` and `processor`.
3. Run the CLI directly:
   ```bash
   uv run exocort
   ```
   The `exocort` command is the package entry point and starts the runner automatically.
If your config file lives somewhere else, pass it explicitly:
   ```bash
   uv run exocort --config /path/to/config.yaml
   ```

The processor watches the configured folder recursively with filesystem events, sends supported image files to OCR and audio files to transcription using LiteLLM-compatible endpoints, and stores a normalized JSON file in the configured output folder while preserving the relative directory structure.

Configuration layout
--------------------

The YAML is organized in two top-level sections:

- `capturer.audio`: audio capture settings and retention for raw audio files.
- `capturer.screen`: screenshot capture settings and retention for raw image files.
- `processor.ocr`: OCR endpoint settings and retention for processed OCR JSON artifacts.
- `processor.asr`: ASR endpoint settings and retention for processed ASR JSON artifacts.
- `processor.notes`: note generation settings.

Example:

```yaml
capturer:
  audio:
    enabled: true
    output_dir: ../tmp/raw/audio
    expired_in: 300
  screen:
    enabled: true
    output_dir: ../tmp/raw/screen
    expired_in: 60

processor:
  enabled: true
  watch_dir: ../tmp/raw
  output_dir: ../tmp/processed
  ocr:
    model: mistral/mistral-ocr-latest
    api_base: http://127.0.0.1:9093/v1
    api_key_env: LITELLM_API_KEY
    expired_in: 600
  asr:
    model: openai/whisper
    api_base: http://127.0.0.1:9092/v1
    api_key_env: LITELLM_API_KEY
    expired_in: 600
  notes:
    enabled: true
    vault_dir: ../vault
```

Retention with `expired_in`
---------------------------

Each `expired_in` value is expressed in seconds and must be `>= 0`.

- `capturer.audio.expired_in`: how long to keep each raw audio file after it has been successfully consumed by ASR.
- `capturer.screen.expired_in`: how long to keep each raw screenshot after it has been successfully consumed by OCR.
- `processor.asr.expired_in`: how long to keep each processed ASR JSON after it has been successfully consumed by `processor.notes`.
- `processor.ocr.expired_in`: how long to keep each processed OCR JSON after it has been successfully consumed by `processor.notes`.

Behavior:

- `expired_in: 0` deletes the file immediately after the successful consumer finishes using it.
- `expired_in: 60` keeps it for 60 seconds after that successful use, then deletes it automatically.
- Files are only scheduled for deletion after a successful handoff. If OCR, ASR, or notes fail, the corresponding file is kept.

Practical examples:

- Set `capturer.audio.expired_in: 0` if you want raw microphone captures to disappear as soon as transcription succeeds.
- Set `capturer.screen.expired_in: 300` if you want screenshots available for five more minutes after OCR.
- Set `processor.asr.expired_in: 0` and `processor.ocr.expired_in: 0` if you want the intermediate JSON artifacts removed as soon as `processor.notes` turns them into note updates.

Expected endpoint contracts
---------------------------

Transcription endpoints must expose `POST /v1/audio/transcriptions` and accept `multipart/form-data`
with at least `file`, `model`, and optionally `language`, `prompt`, `response_format`,
`temperature`. The processor stores only:

```json
{
  "text": "transcribed text"
}
```

OCR endpoints must expose `POST /v1/ocr` and accept `multipart/form-data` with at least
`file` and `model`. The processor stores only:

```json
{
  "text": "recognized text"
}
```

LiteLLM still requires the `model` value to include a real provider prefix (e.g., `openai/…`, `mistral/…`)
even when pointing at an adhoc API base; otherwise the SDK raises `LLM Provider NOT provided`.
