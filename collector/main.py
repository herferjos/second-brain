import os
import uvicorn
from pathlib import Path
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .event_store import EventStore
from .transcribe import transcribe_file
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


def _save_page_content(event: dict) -> None:
    """For page_text events, save content to a file and update event meta."""
    if event.get("type") != "browser.page_text":
        return
    meta = event.get("meta")
    if not isinstance(meta, dict):
        return
    text = meta.get("text")
    if not isinstance(text, str) or not text.strip():
        return

    ts = event.get("ts", utc_now_iso())
    day = ts[:10]
    content_dir = data_dir / "content" / day
    content_dir.mkdir(parents=True, exist_ok=True)

    event_id = event.get("id", new_id())
    content_path = content_dir / f"{ts[:19].replace(':', '-')}-{event_id}.md"
    content_path.write_text(text, encoding="utf-8")

    # Update event meta
    del meta["text"]
    meta["text_path"] = str(content_path.relative_to(data_dir))
    meta["text_preview"] = text[:500]


@app.post("/events")
async def events(payload: dict):
    events_list = payload.get("events") if isinstance(payload, dict) else None
    if isinstance(events_list, list):
        for ev in events_list:
            if isinstance(ev, dict):
                _save_page_content(ev)
                store.append(ev)
        return {"ok": True, "count": len(events_list)}

    if isinstance(payload, dict):
        _save_page_content(payload)
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
    client_source: str | None = Form(default=None),
    page_url: str | None = Form(default=None),
    page_title: str | None = Form(default=None),
):
    seg_id = (segment_id or "").strip() or new_id()
    duration_ms_val = _parse_optional_int(duration_ms)
    rms_val = _parse_optional_int(rms)
    sample_rate_val = _parse_optional_int(sample_rate)
    day = utc_now_iso()[:10]
    out_dir = data_dir / "audio" / day
    out_dir.mkdir(parents=True, exist_ok=True)
    content_type = (file.content_type or "").strip().lower()
    filename = (file.filename or "").strip()
    suffix = ""
    if filename and "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1].lower()
    elif content_type == "audio/webm":
        suffix = ".webm"
    elif content_type in {"audio/ogg", "application/ogg"}:
        suffix = ".ogg"
    elif content_type in {"audio/wav", "audio/x-wav", "audio/wave"}:
        suffix = ".wav"
    elif content_type in {"audio/mpeg", "audio/mp3"}:
        suffix = ".mp3"
    elif content_type in {"audio/mp4", "audio/x-m4a", "audio/m4a"}:
        suffix = ".m4a"
    else:
        suffix = ".bin"

    audio_path = out_dir / f"{seg_id}{suffix}"
    audio_path.write_bytes(await file.read())

    transcript = None
    try:
        transcript = transcribe_file(audio_path, mime_type=content_type or None)
    except Exception:
        transcript = None

    transcript_text = (transcript.text if transcript else None) or ""
    if not transcript_text.strip():
        audio_path.unlink(missing_ok=True)
        return {"ok": True, "event_id": None, "skipped": "no_speech"}

    event = {
        "id": new_id(),
        "ts": utc_now_iso(),
        "source": "audio",
        "type": "audio.segment",
        "meta": {
            "audio_path": str(audio_path),
            "duration_ms": duration_ms_val,
            "vad_reason": (vad_reason or "").strip() or None,
            "rms": rms_val,
            "sample_rate": sample_rate_val,
            "content_type": content_type or None,
            "client_source": (client_source or "").strip() or None,
            "page_url": (page_url or "").strip() or None,
            "page_title": (page_title or "").strip() or None,
            "transcript_text": transcript_text.strip(),
            "transcript_model": (transcript.model if transcript else None),
            "language": (transcript.language if transcript else None),
        },
    }
    store.append(event)
    return {"ok": True, "event_id": event["id"]}


if __name__ == "__main__":
    host = os.getenv("COLLECTOR_HOST", "127.0.0.1")
    port = int(os.getenv("COLLECTOR_PORT", "8787"))
    uvicorn.run(app, host=host, port=port)
