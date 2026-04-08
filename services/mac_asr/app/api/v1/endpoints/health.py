from __future__ import annotations

from fastapi import APIRouter

from src.asr import ensure_speech_permission
from src.config import LOCALE

router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "locale": LOCALE.strip() or None,
        "speech_permission": ensure_speech_permission(prompt=False),
    }
