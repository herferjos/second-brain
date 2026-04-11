from __future__ import annotations

from fastapi import APIRouter

from common.models.health import HealthResponse

from src.chat.service import health as health_status

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return health_status()
