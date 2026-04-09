from __future__ import annotations

from fastapi import APIRouter

from common.models.chat import ChatModelListResponse

from src.chat import list_models as list_available_models

router = APIRouter()


@router.get("/v1/models", response_model=ChatModelListResponse)
def list_models() -> ChatModelListResponse:
    return list_available_models()
