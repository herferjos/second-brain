from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from starlette.responses import Response

from common.models.asr import TranscriptionRequest, TranscriptionResponse
from src.transcription import transcribe_path

router = APIRouter()


@router.post("/v1/audio/transcriptions", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    payload: TranscriptionRequest = Depends(TranscriptionRequest.as_form),
) -> TranscriptionResponse | Response:

    tmp_path = Path(gettempdir()) / f"{uuid4().hex}-{file.filename or 'audio'}"
    try:
        tmp_path.write_bytes(await file.read())
        result = transcribe_path(
            tmp_path,
            language=payload.language,
            prompt=payload.prompt,
        )
        if result is None:
            return Response(status_code=204)
        return result
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
