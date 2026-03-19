from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import LlamaCppSettings, load_settings


log = logging.getLogger("llama_cpp")
app = FastAPI(title="Llama.cpp", version="0.1.0")

_settings: LlamaCppSettings | None = None
_llama = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    stop: str | list[str] | None = None
    response_format: dict[str, Any] | None = None
    stream: bool | None = False


def _ensure_model_path(settings: LlamaCppSettings) -> Path:
    if settings.model_path and settings.model_path.exists():
        return settings.model_path

    if not settings.model_id:
        raise RuntimeError("LLAMA_CPP_MODEL_PATH or LLAMA_CPP_MODEL_ID must be set.")

    from huggingface_hub import snapshot_download

    settings.model_dir.mkdir(parents=True, exist_ok=True)
    local_dir = Path(
        snapshot_download(
            repo_id=settings.model_id,
            revision=settings.revision,
            local_dir=str(settings.model_dir),
            local_dir_use_symlinks=False,
            allow_patterns=["*.gguf"],
        )
    )

    if settings.model_file:
        candidate = local_dir / settings.model_file
        if not candidate.exists():
            raise RuntimeError(f"Model file not found: {candidate}")
        return candidate

    ggufs = sorted(local_dir.rglob("*.gguf"))
    if len(ggufs) == 1:
        return ggufs[0]
    if not ggufs:
        raise RuntimeError("No .gguf files found in downloaded model.")
    raise RuntimeError(
        "Multiple .gguf files found. Set LLAMA_CPP_MODEL_FILE to select one."
    )


def _model_name(settings: LlamaCppSettings) -> str:
    if settings.model_id:
        return settings.model_id
    if settings.model_path:
        return settings.model_path.stem
    return "local-llama"


def _load_llama(settings: LlamaCppSettings):
    from llama_cpp import Llama

    model_path = _ensure_model_path(settings)
    kwargs: dict[str, Any] = {
        "model_path": str(model_path),
        "n_ctx": settings.n_ctx,
        "n_gpu_layers": settings.n_gpu_layers,
    }
    if settings.n_threads > 0:
        kwargs["n_threads"] = settings.n_threads
    return Llama(**kwargs)


def _normalize_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for msg in messages:
        content = msg.content
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)
            content_str = "\n".join(text_parts).strip()
        else:
            content_str = (content or "").strip()
        out.append({"role": msg.role, "content": content_str})
    return out


@app.on_event("startup")
def _startup() -> None:
    global _settings, _llama
    _settings = load_settings()
    try:
        _llama = _load_llama(_settings)
    except Exception:
        log.exception("Failed to load llama model")
        raise


@app.get("/health")
def health() -> dict[str, object]:
    return {"ok": _llama is not None}


@app.get("/v1/models")
def list_models() -> dict[str, Any]:
    settings = _settings or load_settings()
    model_name = _model_name(settings)
    return {
        "object": "list",
        "data": [
            {
                "id": model_name,
                "object": "model",
                "owned_by": "local",
            }
        ],
    }


@app.post("/v1/chat/completions")
def chat_completions(payload: ChatCompletionRequest) -> dict[str, Any]:
    if payload.stream:
        raise HTTPException(status_code=400, detail="streaming is not supported")
    if _llama is None:
        raise HTTPException(status_code=503, detail="model not loaded")

    settings = _settings or load_settings()
    model_name = _model_name(settings)
    messages = _normalize_messages(payload.messages)
    temperature = payload.temperature if payload.temperature is not None else settings.temperature

    try:
        kwargs: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": payload.max_tokens,
            "top_p": payload.top_p,
            "stop": payload.stop,
        }
        if payload.response_format is not None:
            kwargs["response_format"] = payload.response_format
        response = _llama.create_chat_completion(**kwargs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not isinstance(response, dict):
        try:
            response = json.loads(response)
        except Exception:
            raise HTTPException(status_code=500, detail="invalid model response")

    response.setdefault("id", f"chatcmpl-{int(time.time() * 1000)}")
    response.setdefault("object", "chat.completion")
    response.setdefault("created", int(time.time()))
    response.setdefault("model", payload.model or model_name)
    response.setdefault("choices", [])
    response.setdefault("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    return response


def main() -> None:
    import uvicorn

    settings = load_settings()
    uvicorn.run("src.app:app", host=settings.host, port=settings.port, reload=False)


__all__ = ["app", "main"]
