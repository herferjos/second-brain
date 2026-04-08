from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.responses import Response

from src.transcription import transcribe_path

router = APIRouter()


@router.post("/v1/audio/transcriptions")
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
        tmp_path.write_bytes(await file.read())
        payload = transcribe_path(tmp_path, language=language, prompt=prompt)
        if payload is None:
            return Response(status_code=204)
        return payload
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
