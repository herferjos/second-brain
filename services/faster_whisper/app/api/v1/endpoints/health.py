from __future__ import annotations

from fastapi import APIRouter

from common.models.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()
