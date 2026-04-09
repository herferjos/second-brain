from __future__ import annotations

from fastapi import APIRouter

from src.health.models import OcrHealthResponse

router = APIRouter()


@router.get("/health", response_model=OcrHealthResponse)
def health() -> OcrHealthResponse:
    return OcrHealthResponse()
