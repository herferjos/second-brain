import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .event_store import EventStore
from .openai_transcribe import transcribe_wav
from .util import new_id, utc_now_iso

load_dotenv()
data_dir = Path(os.getenv("COLLECTOR_DATA_DIR", "data")).expanduser()
store = EventStore(data_dir=data_dir)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/events")
async def events(payload: dict):
    events_list = payload.get("events") if isinstance(payload, dict) else None
    if isinstance(events_list, list):
        for ev in events_list:
            store.append(ev)
        return {"ok": True, "count": len(events_list)}

    if isinstance(payload, dict):
        store.append(payload)
        return {"ok": True, "count": 1}

    return {"ok": False, "error": "invalid_payload"}


def _parse_optional_int(v: str | int | None) -> int | None:
    if v is None:
        return None
    if isinstance(v, int):
        return v
    s = (v or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


@app.post("/audio")
async def audio(
    file: UploadFile = File(...),
    segment_id: str | None = Form(default=None),
    duration_ms: str | None = Form(default=None),
    vad_reason: str | None = Form(default=None),
    rms: str | None = Form(default=None),
    sample_rate: str | None = Form(default=None),
):
    seg_id = (segment_id or "").strip() or new_id()
    duration_ms_val = _parse_optional_int(duration_ms)
    rms_val = _parse_optional_int(rms)
    sample_rate_val = _parse_optional_int(sample_rate)
    day = utc_now_iso()[:10]
    out_dir = data_dir / "audio" / day
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / f"{seg_id}.wav"
    wav_path.write_bytes(await file.read())

    transcript = None
    try:
        transcript = transcribe_wav(wav_path)
    except Exception:
        transcript = None

    transcript_text = (transcript.text if transcript else None) or ""
    if not transcript_text.strip():
        wav_path.unlink(missing_ok=True)
        return {"ok": True, "event_id": None, "skipped": "no_speech"}

    event = {
        "id": new_id(),
        "ts": utc_now_iso(),
        "source": "audio",
        "type": "audio.segment",
        "meta": {
            "audio_path": str(wav_path),
            "duration_ms": duration_ms_val,
            "vad_reason": (vad_reason or "").strip() or None,
            "rms": rms_val,
            "sample_rate": sample_rate_val,
            "transcript_text": transcript_text.strip(),
            "transcript_model": (transcript.model if transcript else None),
            "language": (transcript.language if transcript else None),
        },
    }
    store.append(event)
    return {"ok": True, "event_id": event["id"]}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("COLLECTOR_HOST", "127.0.0.1")
    port = int(os.getenv("COLLECTOR_PORT", "8787"))
    uvicorn.run(app, host=host, port=port)
