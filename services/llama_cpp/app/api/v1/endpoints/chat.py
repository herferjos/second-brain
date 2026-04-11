from __future__ import annotations

from fastapi import APIRouter

from common.models.chat import ChatCompletionRequest, ChatCompletionResponse

from src.chat.service import chat_completions as create_chat_completion

router = APIRouter()


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def chat_completions(payload: ChatCompletionRequest) -> ChatCompletionResponse:
    return create_chat_completion(payload)
