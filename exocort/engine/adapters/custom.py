"""Custom format: declarative request/response mapping from config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from engine.config import build_http_headers
from engine.unified_config import EndpointSpec
from .base import ChatAdapter, TranscriptionAdapter


def _apply_path(payload: Any, path: str | None) -> Any:
    if not path:
        return payload
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _str_value(val: Any) -> str:
    if isinstance(val, str):
        return val.strip()
    if val is None:
        return ""
    return str(val).strip()


class CustomChatAdapter(ChatAdapter):
    """Uses custom_request / response_path from EndpointSpec."""

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
        template = spec.custom_request if isinstance(spec.custom_request, dict) else {}
        body: dict[str, Any] = dict(template)
        # Allow placeholders; minimal substitution for common keys
        for key, value in list(body.items()):
            if isinstance(value, str):
                body[key] = (
                    value.replace("{{system}}", system)
                    .replace("{{user}}", user)
                    .replace("{{model}}", model or spec.model or "")
                )
        if "model" not in body and (model or spec.model):
            body["model"] = model or spec.model
        if "messages" not in body:
            body["messages"] = [
                {"role": "system", "content": system} if system.strip() else None,
                {"role": "user", "content": user},
            ]
            body["messages"] = [m for m in body["messages"] if m is not None]
        if temperature is not None and "temperature" not in body:
            body["temperature"] = temperature
        if max_tokens is not None and "max_tokens" not in body:
            body["max_tokens"] = max_tokens
        return body

    def parse_response(self, payload: dict[str, Any], spec: EndpointSpec | None = None) -> str:
        path = spec.response_path if spec else None
        if path:
            out = _apply_path(payload, path)
            return _str_value(out)
        return _str_value(payload.get("text") or payload.get("content") or "")


class CustomTranscriptionAdapter(TranscriptionAdapter):
    """Multipart form with optional custom_request; response_path for extraction."""

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
        data: dict[str, str] = {"model": model or spec.model or "transcription"}
        if prompt and prompt.strip():
            data["prompt"] = prompt.strip()
        if language and language.strip():
            data["language"] = language.strip()
        mime_type = "application/octet-stream"
        try:
            import mimetypes
            mt, _ = mimetypes.guess_type(str(file_path))
            if mt:
                mime_type = mt
        except Exception:
            pass
        files = {"file": (file_path.name, file_path.open("rb"), mime_type)}
        return data, files

    def parse_response(self, payload: dict[str, Any], spec: EndpointSpec | None = None) -> str:
        path = spec.response_path if spec else None
        if path:
            out = _apply_path(payload, path)
            return _str_value(out)
        return _str_value(payload.get("text") or payload.get("content") or "")
