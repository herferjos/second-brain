# Frame Capture (Screen OCR → LifeLog Collector)

Captures screen frames on macOS, runs **local** OCR with **LightOnOCR-2-1B** (Transformers), and sends the extracted Markdown to the LifeLog collector. **The collector** saves each frame’s markdown under `data/frame/` (same idea as audio: collector stores files in `data/audio/`). No API key required.

## Setup

1. **Install dependencies** (from repo root or `frame_capture/`):
   ```bash
   pip install -r frame_capture/requirements.txt
   ```
   Requires **transformers >= 5.0**, **torch**, **Pillow**, **pypdfium2**. Uses MPS on Apple Silicon, CUDA if available, else CPU.

2. **Environment** – optional; create `frame_capture/.env` or set in shell:
   - `FRAME_CAPTURE_COLLECTOR_EVENTS_URL` – default `http://127.0.0.1:8787/events`. Set to empty to disable sending to the collector (then frame_capture writes .md to `FRAME_CAPTURE_OUTPUT_DIR` as fallback).
   - `FRAME_CAPTURE_NUM_FRAMES` – number of frames to capture (default `10`).
   - `FRAME_CAPTURE_DELAY_S` – seconds between captures (default `1.0`).
   - `FRAME_CAPTURE_OUTPUT_DIR` – directory for PNG screenshots (default `outputs`); also used for local .md only when collector is disabled.
   - `FRAME_CAPTURE_MAX_NEW_TOKENS` – max tokens per OCR output (default `1024`).
   - `FRAME_CAPTURE_MAX_IMAGE_SIZE` – resize longest side to this (default `1540`).

3. **Start the collector** (in a separate terminal), so frame events are stored under `data/frame/`:
   ```bash
   pip install -r collector/requirements.txt
   python -m uvicorn collector.main:app --host 127.0.0.1 --port 8787
   ```

4. **Run frame capture** (from repo root):
   ```bash
   set -a && source frame_capture/.env && set +a
   python frame_capture/main.py
   ```
   Or from `frame_capture/`:
   ```bash
   cd frame_capture && python main.py
   ```

## Data layout

- **Collector** (when frame_capture sends to it) writes each frame’s markdown to **`data/frame/YYYY-MM-DD/<timestamp>-<event_id>.md`** and appends the event to **`data/events/YYYY-MM-DD.jsonl`** with `type: "frame.capture"` and `source: "frame_capture"`. Same pattern as audio: collector receives and stores.
- If `FRAME_CAPTURE_COLLECTOR_EVENTS_URL` is empty, frame_capture writes .md into `FRAME_CAPTURE_OUTPUT_DIR` instead (no collector).

## Notes

- **macOS** – screen capture uses `mss` and Pillow. Python 3.10+.
- **OCR** – local **lightonai/LightOnOCR-2-1B** via Transformers (no API key). First run downloads the model from Hugging Face.
