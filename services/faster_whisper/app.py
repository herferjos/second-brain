from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from starlette.responses import Response

from config import FasterWhisperSettings, load_settings


def _create_model(settings: FasterWhisperSettings):
    from faster_whisper import WhisperModel

    return WhisperModel(
        settings.model_path,
        device=settings.device,
        compute_type=settings.compute_type,
    )


settings = load_settings()
model = None

app = FastAPI(title="Faster Whisper", version="0.1.0")


def get_model():
    global model
    if model is None:
        model = _create_model(settings)
    return model


@app.post("/v1/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    model: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
    prompt: Annotated[str | None, Form()] = None,
    response_format: Annotated[str | None, Form()] = None,
    temperature: Annotated[float | None, Form()] = None,
) -> Response | dict[str, object]:
    del model, temperature
    if response_format not in (None, "", "json"):
        raise HTTPException(status_code=400, detail="Only response_format=json is supported.")
    tmp_path = Path(gettempdir()) / f"{uuid4().hex}-{file.filename or 'audio'}"
    try:
        content = await file.read()
        tmp_path.write_bytes(content)

        segments, info = get_model().transcribe(
            str(tmp_path),
            beam_size=settings.beam_size,
            language=language or settings.language,
            initial_prompt=prompt or None,
        )

        text_parts: list[str] = [segment.text.strip() for segment in segments if segment.text]
        text = " ".join(text_parts).strip()
        if not text:
            return Response(status_code=204)
        return {
            "text": text,
            "task": "transcribe",
            "language": language or settings.language,
            "duration": None,
        }
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            # Best-effort cleanup; ignore errors
            pass


import os

def main() -> None:
    import uvicorn

    host = os.environ.get("FASTER_WHISPER_HOST", "127.0.0.1")
    port = int(os.environ.get("FASTER_WHISPER_PORT", 9000))

    uvicorn.run("app:app", host=host, port=port, reload=True)


__all__ = ["app", "get_model", "main"]
