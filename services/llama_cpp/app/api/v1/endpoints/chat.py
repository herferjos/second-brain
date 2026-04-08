from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.chat import ChatCompletionRequest, chat_completions as create_chat_completion

router = APIRouter()


@router.post("/v1/chat/completions")
def chat_completions(payload: ChatCompletionRequest) -> dict[str, Any]:
    return create_chat_completion(payload)
