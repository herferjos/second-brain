from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatContentPart(BaseModel):
    type: str
    text: str | None = None

    model_config = ConfigDict(extra="allow")


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[ChatContentPart] | None = None


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    stop: str | list[str] | None = None
    response_format: dict[str, object] | None = None
    stream: bool | None = False


class ChatCompletionChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str | None = None

    model_config = ConfigDict(extra="allow")


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionChoiceMessage
    finish_reason: str | None = None

    model_config = ConfigDict(extra="allow")


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice] = Field(default_factory=list)
    usage: ChatCompletionUsage

    model_config = ConfigDict(extra="allow")


class ChatModel(BaseModel):
    id: str
    object: Literal["model"] = "model"
    owned_by: str


class ChatModelListResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[ChatModel]


__all__ = [
    "ChatCompletionChoice",
    "ChatCompletionChoiceMessage",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatCompletionUsage",
    "ChatContentPart",
    "ChatMessage",
    "ChatModel",
    "ChatModelListResponse",
]
