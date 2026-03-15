from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .asr import ensure_speech_permission, transcribe_audio_file
from .config import (
    HOST,
    LOCALE,
    PORT,
    PROMPT_PERMISSION,
    TRANSCRIPTION_TIMEOUT_S,
)


app = FastAPI(title="Mac ASR", version="0.1.0")


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "locale": LOCALE,
        "speech_permission": ensure_speech_permission(prompt=False),
    }


@app.post("/v1/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Annotated[str | None, Form()] = None,
    model: Annotated[str | None, Form()] = None,
    prompt: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    del model, prompt

    if not ensure_speech_permission(prompt=PROMPT_PERMISSION):
        raise HTTPException(
            status_code=409,
            detail="Speech recognition permission is required.",
        )

    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        path = Path(tmp.name)
    try:
        path.write_bytes(await file.read())
        result = transcribe_audio_file(
            path,
            locale=language or LOCALE,
            timeout_s=TRANSCRIPTION_TIMEOUT_S,
        )
        return result.to_dict()
    finally:
        path.unlink(missing_ok=True)


def main() -> None:
    import uvicorn
    if not ensure_speech_permission(prompt=PROMPT_PERMISSION):
        raise RuntimeError("Speech recognition permission is required.")
    uvicorn.run("src.app:app", host=HOST, port=PORT, reload=False)
