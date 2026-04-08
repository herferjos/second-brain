from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.transcriptions import router as transcriptions_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(transcriptions_router)
