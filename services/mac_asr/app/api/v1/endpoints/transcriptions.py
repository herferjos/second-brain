from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.responses import Response

from common.models.asr import TranscriptionRequest, TranscriptionResponse
from common.utils.logs import get_logger
from src.asr.permissions import ensure_speech_permission
from src.asr.errors import _is_no_speech_error
from src.asr.transcription import transcribe_audio_file
from src.config.settings import load_settings
from src.transcription import resolve_request_locale, transcription_text

log = get_logger("mac_asr", "api")

router = APIRouter()


@router.post("/v1/audio/transcriptions", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    payload: TranscriptionRequest = Depends(TranscriptionRequest.as_form),
) -> TranscriptionResponse | Response:
    settings = load_settings()
    log.debug(
        "Received ASR request | filename=%s | model=%s | language=%s | response_format=%s | temperature=%s",
        file.filename,
        payload.model,
        payload.language,
        payload.response_format,
        payload.temperature,
    )
    if not ensure_speech_permission(prompt=settings.prompt_permission):
        raise HTTPException(
            status_code=409,
            detail="Speech recognition permission is required.",
        )

    path = Path(gettempdir()) / f"{uuid4().hex}.wav"
    try:
        path.write_bytes(await file.read())
        log.debug("Stored ASR temp audio | path=%s | filename=%s", path, file.filename)
        locale = resolve_request_locale(path, payload.language)
        log.debug("Resolved ASR locale | requested=%s | resolved=%s", payload.language, locale)
        if not locale:
            log.debug("Skipping ASR request with empty locale | path=%s", path)
            return Response(status_code=204)
        try:
            result = transcribe_audio_file(
                path,
                locale=locale,
                timeout_s=settings.transcription_timeout_s,
            )
            text = transcription_text(result)
            if not text:
                log.info(
                    "Empty transcription | locale=%s | file=%s",
                    locale,
                    file.filename,
                )
                return Response(status_code=204)
            log.debug(
                "ASR response ready | path=%s | locale=%s | text_len=%s",
                path,
                locale,
                len(text),
            )
            return TranscriptionResponse(
                text=text,
                language=locale,
                duration=None,
            )
        except RuntimeError as exc:
            if _is_no_speech_error(str(exc)):
                log.info(
                    "No speech detected | locale=%s | file=%s",
                    locale,
                    file.filename,
                )
                return Response(status_code=204)
            raise
    finally:
        log.debug("Cleaning ASR temp audio | path=%s", path)
        path.unlink(missing_ok=True)
