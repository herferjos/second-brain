from __future__ import annotations

from fastapi import APIRouter

from src.asr import ensure_speech_permission
from src.config import load_settings
from src.health.models import AsrHealthResponse

router = APIRouter()


@router.get("/health", response_model=AsrHealthResponse)
def health() -> AsrHealthResponse:
    settings = load_settings()
    return AsrHealthResponse(
        locale=settings.locale.strip() or None,
        speech_permission=ensure_speech_permission(prompt=False),
    )
