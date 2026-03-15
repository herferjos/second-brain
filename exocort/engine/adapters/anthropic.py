"""Anthropic-compatible wire format (chat only)."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from engine.config import build_http_headers, guess_mime_type
from engine.unified_config import EndpointSpec
from .base import ChatAdapter


def _schema_prompt(output_model: type[BaseModel]) -> str:
    schema = json.dumps(output_model.model_json_schema(), ensure_ascii=False, indent=2)
    return "Return only valid JSON that matches this schema exactly.\n\n" + schema


def _extract_anthropic_text(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != "text":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n".join(parts).strip()


class AnthropicChatAdapter(ChatAdapter):
    def build_headers(
        self,
        spec: EndpointSpec,
        api_key: str,
        anthropic_version: str | None = None,
    ) -> dict[str, str]:
        return build_http_headers(
            format_name="anthropic",
            api_key=api_key,
            headers=spec.headers,
            api_key_header=spec.api_key_header,
            auth_scheme=spec.auth_scheme,
            anthropic_version=anthropic_version or "2023-06-01",
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
        if audio_path is not None:
            raise ValueError("Anthropic chat audio is not supported")

        user_content_blocks: list[dict[str, Any]] = []
        final_user = user.strip()
        if output_model is not None:
            final_user = f"{final_user}\n\n{_schema_prompt(output_model)}".strip()
        if final_user:
            user_content_blocks.append({"type": "text", "text": final_user})
        if image_path is not None:
            mime_type = guess_mime_type(image_path, "image/png")
            user_content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": base64.b64encode(image_path.read_bytes()).decode("utf-8"),
                },
            })

        payload: dict[str, Any] = {
            "model": model or spec.model,
            "messages": [{"role": "user", "content": user_content_blocks or final_user}],
            "max_tokens": max_tokens or 1024,
        }
        if system.strip():
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        return payload

    def parse_response(self, payload: dict[str, Any], spec: EndpointSpec | None = None) -> str:
        return _extract_anthropic_text(payload)
