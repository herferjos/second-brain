from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.chat import list_models as list_available_models

router = APIRouter()


@router.get("/v1/models")
def list_models() -> dict[str, Any]:
    return list_available_models()
