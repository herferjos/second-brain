"""OpenAI-compatible wire format (chat + transcription)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from engine.config import build_http_headers, guess_mime_type
from engine.unified_config import EndpointSpec
from .base import ChatAdapter, TranscriptionAdapter


def _data_uri(path: Path, fallback_mime_type: str) -> str:
    mime_type = guess_mime_type(path, fallback_mime_type)
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def _audio_format(mime_type: str) -> str:
    value = (mime_type or "").strip().lower()
    if "/" in value:
        value = value.split("/", 1)[1]
    aliases = {"x-wav": "wav", "wave": "wav", "mpeg": "mp3", "x-m4a": "m4a"}
    return aliases.get(value, value or "wav")


def _extract_openai_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        if item_type in {"text", "output_text"}:
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts).strip()


def _openai_chat_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    return _extract_openai_content(message.get("content"))


def _openai_response_schema(output_model: type[BaseModel]) -> dict[str, Any]:
    def normalize(node: Any) -> Any:
        if isinstance(node, list):
            return [normalize(item) for item in node]
        if not isinstance(node, dict):
            return node
        normalized = {key: normalize(value) for key, value in node.items()}
        if normalized.get("type") == "object":
            normalized["additionalProperties"] = False
            properties = normalized.get("properties")
            if isinstance(properties, dict):
                normalized["required"] = list(properties.keys())
        return normalized

    import json
    raw_schema = output_model.model_json_schema()
    return normalize(raw_schema)


class OpenAIChatAdapter(ChatAdapter):
    def build_headers(
        self,
        spec: EndpointSpec,
        api_key: str,
        anthropic_version: str | None = None,
    ) -> dict[str, str]:
        return build_http_headers(
            format_name="openai",
            api_key=api_key,
            headers=spec.headers,
            api_key_header=spec.api_key_header,
            auth_scheme=spec.auth_scheme,
        )

    def build_body(
        self,
        spec: EndpointSpec,
        system: str,
        user: str,
        timeout_s: float,
        *,
        model: str | None = None,
        image_path: Path | None = None,
        audio_path: Path | None = None,
        audio_mime_type: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        output_model: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or spec.model,
            "messages": [],
        }
        if system.strip():
            payload["messages"].append({"role": "system", "content": system})

        user_content: list[dict[str, Any]] = []
        if user.strip():
            user_content.append({"type": "text", "text": user})
        if image_path is not None:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": _data_uri(image_path, "image/png")},
            })
        if audio_path is not None:
            mime_type = audio_mime_type or guess_mime_type(audio_path, "audio/wav")
            user_content.append({
                "type": "input_audio",
                "input_audio": {
                    "data": base64.b64encode(audio_path.read_bytes()).decode("utf-8"),
                    "format": _audio_format(mime_type),
                },
            })
        payload["messages"].append({
            "role": "user",
            "content": user_content if user_content else user,
        })

        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if output_model is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": output_model.__name__,
                    "strict": True,
                    "schema": _openai_response_schema(output_model),
                },
            }
        return payload

    def parse_response(self, payload: dict[str, Any], spec: EndpointSpec | None = None) -> str:
        return _openai_chat_text(payload)


class OpenAITranscriptionAdapter(TranscriptionAdapter):
    def build_headers(self, spec: EndpointSpec, api_key: str) -> dict[str, str]:
        h = build_http_headers(
            format_name="openai",
            api_key=api_key,
            headers=spec.headers,
            api_key_header=spec.api_key_header,
            auth_scheme=spec.auth_scheme,
        )
        h.pop("content-type", None)
        return h

    def build_form_data(
        self,
        spec: EndpointSpec,
        file_path: Path,
        *,
        model: str | None = None,
        language: str | None = None,
        prompt: str | None = None,
    ) -> tuple[dict[str, str], dict[str, tuple[str, Any, str]]]:
        mime_type = guess_mime_type(file_path, "application/octet-stream")
        data: dict[str, str] = {"model": model or spec.model or "transcription"}
        if prompt and prompt.strip():
            data["prompt"] = prompt.strip()
        if language and language.strip():
            data["language"] = language.strip()
        files = {"file": (file_path.name, file_path.open("rb"), mime_type)}
        return data, files

    def parse_response(self, payload: dict[str, Any], spec: EndpointSpec | None = None) -> str:
        text = payload.get("text")
        if isinstance(text, str):
            return text.strip()
        return ""
