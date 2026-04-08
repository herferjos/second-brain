from __future__ import annotations

from fastapi import APIRouter

from src.chat import health as health_status

router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    return health_status()
