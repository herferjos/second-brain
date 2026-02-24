# LifeLog Collector

Local HTTP service that receives events from the Chrome extension and audio capture, appends them to daily JSONL files, and transcribes audio via OpenAI.

## Setup

1. Install dependencies:
   ```bash
   pip install -r collector/requirements.txt
   ```

2. Create env file:
   ```bash
   cp collector/.env.example collector/.env
   ```

3. Set `OPENAI_API_KEY` in `.env` for audio transcription.

4. Run:
   ```bash
   python -m uvicorn collector.main:app --host 127.0.0.1 --port 8787
   ```
   Or:
   ```bash
   python -m collector.main
   ```

## Endpoints

- `GET /healthz` – health check
- `POST /events` – append events (JSON body: single event or `{"events": [...]}`)
- `POST /audio` – upload wav file (multipart: `file`, optional: `segment_id`, `duration_ms`, `vad_reason`, `rms`, `sample_rate`)

## Data layout

- `data/events/YYYY-MM-DD.jsonl` – one event per line
- `data/audio/YYYY-MM-DD/<segment_id>.wav` – audio segments
