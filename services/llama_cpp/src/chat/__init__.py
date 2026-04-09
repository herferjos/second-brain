from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from fastapi import HTTPException
from huggingface_hub import hf_hub_download
from llama_cpp import Llama

from common.models.chat import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatContentPart,
    ChatModel,
    ChatModelListResponse,
    ChatMessage,
)
from common.models.health import HealthResponse
from common.utils.logs import get_logger

from ..config import LlamaCppSettings, load_settings


log = get_logger("llama_cpp")

_settings: LlamaCppSettings | None = None
_llama: Llama | None = None
_llama_lock = threading.Lock()


def _model_name(settings: LlamaCppSettings) -> str:
    return settings.model_id


def _ensure_model_path(settings: LlamaCppSettings) -> Path:
    model_name = settings.model_id.split("/")[-1].replace("-GGUF", "")
    filename = f"{model_name}-{settings.quantization}.gguf"
    local_path = settings.model_dir / filename
    if local_path.exists():
        return local_path

    settings.model_dir.mkdir(parents=True, exist_ok=True)
    hf_hub_download(
        repo_id=settings.model_id,
        filename=filename,
        local_dir=str(settings.model_dir),
        local_dir_use_symlinks=False,
    )
    return local_path


def _load_llama(settings: LlamaCppSettings) -> Llama:
    model_path = _ensure_model_path(settings)
    kwargs: dict[str, object] = {
        "model_path": str(model_path),
        "n_ctx": settings.n_ctx,
        "n_gpu_layers": settings.n_gpu_layers,
        "n_batch": settings.n_batch,
        "seed": settings.seed,
    }
    if settings.n_threads > 0:
        kwargs["n_threads"] = settings.n_threads
    return Llama(**kwargs)


def _normalize_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for msg in messages:
        content = msg.content
        if isinstance(content, list):
            text_parts: list[str] = [
                item.text.strip()
                for item in content
                if item.text is not None and item.text.strip()
            ]
            content_str = "\n".join(text_parts).strip()
        else:
            content_str = (content or "").strip()
        out.append({"role": msg.role, "content": content_str})
    return out


def startup() -> None:
    global _settings, _llama
    _settings = load_settings()
    try:
        _llama = _load_llama(_settings)
    except Exception:
        log.exception("Failed to load llama model")
        raise


def health() -> HealthResponse:
    return HealthResponse(ok=_llama is not None)


def list_models() -> ChatModelListResponse:
    settings = _settings or load_settings()
    model_name = _model_name(settings)
    return ChatModelListResponse(
        data=[
            ChatModel(
                id=model_name,
                owned_by="local",
            )
        ]
    )


def chat_completions(payload: ChatCompletionRequest) -> ChatCompletionResponse:
    if payload.stream:
        raise HTTPException(status_code=400, detail="streaming is not supported")
    if _llama is None:
        raise HTTPException(status_code=503, detail="model not loaded")

    settings = _settings or load_settings()
    model_name = _model_name(settings)
    messages = _normalize_messages(payload.messages)
    temperature = payload.temperature if payload.temperature is not None else settings.temperature

    try:
        kwargs: dict[str, object] = {
            "messages": messages,
            "temperature": temperature,
        }
        if payload.max_tokens is not None:
            kwargs["max_tokens"] = payload.max_tokens
        if payload.top_p is not None:
            kwargs["top_p"] = payload.top_p
        if payload.stop is not None:
            kwargs["stop"] = payload.stop
        if payload.response_format is not None:
            kwargs["response_format"] = payload.response_format
        with _llama_lock:
            response: object = _llama.create_chat_completion(**kwargs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if isinstance(response, dict):
        response_data: dict[str, object] = response
    else:
        try:
            if not isinstance(response, (str, bytes, bytearray)):
                raise TypeError("invalid model response")
            loaded_response = json.loads(response)
        except Exception:
            raise HTTPException(status_code=500, detail="invalid model response")
        if not isinstance(loaded_response, dict):
            raise HTTPException(status_code=500, detail="invalid model response")
        response_data = loaded_response

    response_data.setdefault("id", f"chatcmpl-{int(time.time() * 1000)}")
    response_data.setdefault("object", "chat.completion")
    response_data.setdefault("created", int(time.time()))
    response_data.setdefault("model", payload.model or model_name)
    response_data.setdefault("choices", [])
    response_data.setdefault(
        "usage",
        {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    )
    return ChatCompletionResponse.model_validate(response_data)


__all__ = [
    "ChatCompletionChoice",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatCompletionUsage",
    "ChatContentPart",
    "ChatMessage",
    "ChatModel",
    "ChatModelListResponse",
    "chat_completions",
    "health",
    "list_models",
    "startup",
]
