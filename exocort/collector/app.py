"""Collector API: receives capture uploads and forwards to configured processing endpoints."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, UploadFile

from .config import CollectorConfig
from .forward import forward_upload
from .vault import save_to_tmp, remove_tmp, write_vault_record

log = logging.getLogger("collector")

_config: CollectorConfig | None = None


def get_config() -> CollectorConfig:
    global _config
    if _config is None:
        _config = CollectorConfig.load()
    return _config


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_config()
    yield
    pass


app = FastAPI(title="Exocort Collector", lifespan=lifespan)


def _now() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d"), now.isoformat()


@app.post("/api/audio")
async def api_audio(
    file: UploadFile = File(...),
    segment_id: str = Form(""),
    sample_rate: str = Form(""),
    client_source: str = Form(""),
    source: str = Form(""),
    duration_ms: str = Form(""),
    vad_reason: str = Form(""),
    rms: str = Form(""),
):
    """Receive audio from capture agent; save to tmp, forward, persist responses to vault, remove tmp."""
    config = get_config()
    body = await file.read()
    form_data = {
        "segment_id": segment_id,
        "sample_rate": sample_rate,
        "client_source": client_source,
        "source": source,
        "duration_ms": duration_ms,
        "vad_reason": vad_reason,
        "rms": rms,
    }
    segment_id = segment_id or _now()[1].replace(":", "-")
    filename = file.filename or "audio.wav"
    content_type = file.content_type or "audio/wav"

    if not config.audio:
        return {"ok": True, "forwarded": 0, "message": "No audio endpoints configured"}

    date, timestamp_iso = _now()
    safe_ts = timestamp_iso.replace(":", "-")
    tmp_path = save_to_tmp(body, "audio", date, f"{safe_ts}_{segment_id}", ".wav")
    try:
        results = []
        for ep in config.audio:
            ok, status, resp_body = forward_upload(
                ep, body, filename, content_type, form_data
            )
            results.append({"url": ep.url, "ok": ok, "status": status, "body": resp_body})

        vault_path = write_vault_record(
            date, timestamp_iso, "audio", segment_id, form_data, results
        )
        log.info("Vault wrote | path=%s", vault_path)
        return {"ok": True, "forwarded": len(config.audio), "results": [{"url": r["url"], "ok": r["ok"], "status": r["status"]} for r in results]}
    finally:
        remove_tmp(tmp_path)


@app.post("/api/screen")
async def api_screen(
    file: UploadFile = File(...),
    screen_id: str = Form(""),
    width: str = Form(""),
    height: str = Form(""),
    hash: str = Form(""),  # noqa: A002
    app_json: str = Form("", alias="app"),
    capture: str = Form(""),
    permissions: str = Form(""),
    window: str = Form(""),
):
    """Receive screen capture; save to tmp, forward, persist responses to vault, remove tmp."""
    config = get_config()
    body = await file.read()
    form_data = {
        "screen_id": screen_id,
        "width": width,
        "height": height,
        "hash": hash,
        "app": app_json,
        "capture": capture,
        "permissions": permissions,
    }
    if window:
        form_data["window"] = window
    screen_id = screen_id or _now()[1].replace(":", "-")
    filename = file.filename or "screen.png"
    content_type = file.content_type or "image/png"

    if not config.screen:
        return {"ok": True, "forwarded": 0, "message": "No screen endpoints configured"}

    date, timestamp_iso = _now()
    safe_ts = timestamp_iso.replace(":", "-")
    tmp_path = save_to_tmp(body, "screen", date, f"{safe_ts}_{screen_id}", ".png")
    try:
        results = []
        for ep in config.screen:
            ok, status, resp_body = forward_upload(
                ep, body, filename, content_type, form_data
            )
            results.append({"url": ep.url, "ok": ok, "status": status, "body": resp_body})

        vault_path = write_vault_record(
            date, timestamp_iso, "screen", screen_id, form_data, results
        )
        log.info("Vault wrote | path=%s", vault_path)
        return {"ok": True, "forwarded": len(config.screen), "results": [{"url": r["url"], "ok": r["ok"], "status": r["status"]} for r in results]}
    finally:
        remove_tmp(tmp_path)


def main() -> None:
    import uvicorn

    from exocort import settings

    logging.basicConfig(
        level=settings.log_level(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    host = os.environ.get("COLLECTOR_HOST", "127.0.0.1")
    port = int(os.environ.get("COLLECTOR_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
