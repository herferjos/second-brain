"""Transport and adapter-driven chat/transcription. No SDKs, endpoint URL + format only."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel

from engine.adapters import get_chat_adapter, get_transcription_adapter
from engine.unified_config import EndpointSpec


def _strip_code_fences(text: str) -> str:
    raw = text.strip()
    if raw.startswith("```") and raw.endswith("```"):
        lines = raw.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return raw


def post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any]:
    response = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object response from {url}")
    return data


def post_multipart(
    url: str,
    headers: dict[str, str],
    data: dict[str, str],
    files: dict[str, tuple[str, Any, str]],
    timeout_s: float,
) -> dict[str, Any]:
    try:
        response = requests.post(
            url,
            headers=headers,
            data=data,
            files=files,
            timeout=timeout_s,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object response from {url}")
        return payload
    finally:
        for entry in files.values():
            if len(entry) >= 2 and hasattr(entry[1], "close"):
                try:
                    entry[1].close()
                except Exception:
                    pass


def chat_completion(
    *,
    spec: EndpointSpec,
    api_key: str,
    anthropic_version: str | None,
    system: str,
    user: str,
    timeout_s: float,
    model: str | None = None,
    image_path: Path | None = None,
    audio_path: Path | None = None,
    audio_mime_type: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    output_model: type[BaseModel] | None = None,
) -> str:
    if spec.format == "none" or not spec.endpoint_url:
        raise ValueError("Chat endpoint URL is required")
    adapter = get_chat_adapter(spec.format)
    headers = adapter.build_headers(spec, api_key, anthropic_version)
    body = adapter.build_body(
        spec,
        system,
        user,
        timeout_s,
        model=model or spec.model,
        image_path=image_path,
        audio_path=audio_path,
        audio_mime_type=audio_mime_type,
        temperature=temperature,
        max_tokens=max_tokens,
        output_model=output_model,
    )
    data = post_json(spec.endpoint_url, headers, body, timeout_s)
    return adapter.parse_response(data, spec if spec.format == "custom" else None)


def transcription(
    *,
    spec: EndpointSpec,
    api_key: str,
    file_path: Path,
    timeout_s: float,
    model: str | None = None,
    language: str | None = None,
    prompt: str | None = None,
) -> str:
    if spec.format == "none" or not spec.endpoint_url:
        raise ValueError("Transcription endpoint URL is required")
    adapter = get_transcription_adapter(spec.format)
    headers = adapter.build_headers(spec, api_key)
    form_data, form_files = adapter.build_form_data(
        spec,
        file_path,
        model=model or spec.model,
        language=language,
        prompt=prompt,
    )
    payload = post_multipart(spec.endpoint_url, headers, form_data, form_files, timeout_s)
    return adapter.parse_response(payload, spec if spec.format == "custom" else None)


def parse_structured_output(raw_text: str, output_model: type[BaseModel]) -> BaseModel:
    cleaned = _strip_code_fences(raw_text)
    try:
        return output_model.model_validate_json(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return output_model.model_validate_json(match.group(0))


def openai_chat_response(text: str, model: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-local-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
