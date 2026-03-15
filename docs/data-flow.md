# Exocort — Data flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CAPTURE AGENTS (local)                            │
├─────────────────────────────────┬─────────────────────────────────────────┤
│  exocort-audio                   │  exocort-screen                          │
│  (mic / system loopback)        │  (screenshots at FPS)                    │
│                                  │                                          │
│  • VAD segments → WAV            │  • PNG screen + metadata               │
│  • Spool → upload when segment   │  • Upload every new screen               │
│    ends                          │                                          │
└──────────────┬───────────────────┴──────────────────┬──────────────────────┘
               │                                       │
               │  POST /api/audio                       │  POST /api/screen
               │  (file + segment_id, sample_rate, …)   │  (file + screen_id, width, …)
               ▼                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  COLLECTOR (exocort-collector)  —  :8000                                    │
│  Config: config.json                                                         │
│  • Receives audio uploads  →  forwards to config.audio.endpoints[]           │
│  • Receives screen uploads  →  forwards to config.screen.endpoints[]        │
└──────────────┬──────────────────────────────────────┬──────────────────────┘
               │                                       │
               │  POST (file + form)                   │  POST (file + form)
               │  to each audio endpoint                │  to each screen endpoint
               ▼                                       ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│  Audio processing APIs       │    │  Image processing APIs       │
│  (e.g. ASR / transcription)   │    │  (e.g. OCR)                  │
│                               │    │                               │
│  Example:                     │    │  Example:                     │
│  mac_asr :9092               │    │  mac_ocr :9091                │
│  /v1/audio/transcriptions     │    │  /ocr                         │
└──────────────────────────────┘    └──────────────────────────────┘
```

## Summary

| Step | Component | Role |
|------|-----------|------|
| 1 | **exocort-audio** | Captures mic (and optionally system audio), segments with VAD, saves WAV to spool, then POSTs each segment to `COLLECTOR_AUDIO_URL` (default collector `/api/audio`). |
| 2 | **exocort-screen** | Captures screen at configured FPS, POSTs each new screen to `COLLECTOR_SCREEN_URL` (default collector `/api/screen`). |
| 3 | **exocort-collector** | Receives uploads on `/api/audio` and `/api/screen`; reads `config.json` and forwards each request to the listed endpoints (same file + form). |
| 4 | **Processing APIs** | External services (ASR, OCR, etc.) receive the forwarded requests and return their results (collector does not store or process the responses). |

## Where is data stored?

| Data | Stored? | Location |
|------|--------|----------|
| **Audio segments (capturer)** | Temporarily | `AUDIO_CAPTURE_SPOOL_DIR` (default `./tmp/audio`). Each segment is a `.wav` + `.wav.meta.json`. **Deleted after successful upload** to the collector. |
| **Screen captures (capturer)** | No | Frames are sent in memory to the collector. `SCREEN_CAPTURE_TMP_DIR` (default `./tmp/screen`) is available if frames are ever written to disk. |
| **Collector tmp** | Briefly | Incoming audio and screen are written to `COLLECTOR_TMP_DIR` (default `./tmp/collector`) under `audio/{date}/` and `screen/{date}/` with timestamped filenames. **Deleted after** forwarding and vault write. |
| **Collector vault** | Yes | API responses (transcription, OCR, etc.) are stored in `COLLECTOR_VAULT_DIR` (default `./vault`). Layout: `vault/{YYYY-MM-DD}/{timestamp}_audio_{id}.json` and `vault/{YYYY-MM-DD}/{timestamp}_screen_{id}.json`. Each JSON has `timestamp`, `type`, `id`, `meta` (form fields), and `responses` (per endpoint: `url`, `status`, `body`). |

Env: per-system temp dirs under `tmp/` — `AUDIO_CAPTURE_SPOOL_DIR`, `SCREEN_CAPTURE_TMP_DIR`, `COLLECTOR_TMP_DIR`; `COLLECTOR_VAULT_DIR` (see `.env.example`). `tmp/` and `vault/` are in `.gitignore`.

## Config

- **Capture agents**: `.env` (or env) — `COLLECTOR_AUDIO_URL`, `COLLECTOR_SCREEN_URL` (collector-defined upload endpoints), plus capture-specific vars.
- **Collector**: `config.json` — `audio.endpoints[]`, `screen.endpoints[]` (url, method, timeout, forward_form, headers).
