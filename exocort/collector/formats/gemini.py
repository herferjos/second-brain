"""Gemini API format: chat/completions with base64 audio or image in messages.

Gemini does not expose /v1/audio/transcriptions; it uses the same OpenAI-compatible
chat/completions endpoint for both audio (input_audio) and vision (image_url).
Request is JSON body, not multipart. Response shape is the same as OpenAI
(choices[0].message.content), so we reuse the same response parsing.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any

from .base import BuiltRequest, FormatAdapter, ParsedResponse
from .openai import _extract_text_from_openai_body

if TYPE_CHECKING:
    from exocort.collector.config import EndpointConfig


def _audio_format_from_content_type(content_type: str) -> str:
    """Map content type to Gemini input_audio format."""
    ct = (content_type or "").lower()
    if "wav" in ct:
        return "wav"
    if "mp3" in ct or "mpeg" in ct:
        return "mp3"
    if "webm" in ct:
        return "webm"
    if "ogg" in ct:
        return "ogg"
    if "flac" in ct:
        return "flac"
    return "wav"


def _image_mime_from_content_type(content_type: str) -> str:
    """Map content type to data URL mime for image."""
    ct = (content_type or "").lower()
    if "png" in ct:
        return "image/png"
    if "jpeg" in ct or "jpg" in ct:
        return "image/jpeg"
    if "webp" in ct:
        return "image/webp"
    return "image/png"


class GeminiAdapter(FormatAdapter):
    """Adapter for Gemini: chat/completions with file as base64 in message content."""

    def build_request(
        self,
        endpoint: "EndpointConfig",
        file_content: bytes,
        filename: str,
        content_type: str,
        stream_type: str,
    ) -> BuiltRequest:
        body = endpoint.body or {}
        model = body.get("model", "gemini-2.0-flash")
        prompt = body.get("prompt", "").strip()
        body_extra = {k: v for k, v in body.items() if k not in ("model", "prompt")}
        b64 = base64.b64encode(file_content).decode("ascii")

        if stream_type == "audio":
            if not prompt:
                prompt = "Transcribe the attached audio."
            fmt = _audio_format_from_content_type(content_type)
            content = [
                {"type": "text", "text": prompt},
                {"type": "input_audio", "input_audio": {"data": b64, "format": fmt}},
            ]
        else:
            if not prompt:
                prompt = "Describe or transcribe everything visible in the attached image."
            mime = _image_mime_from_content_type(content_type)
            content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
        }
        if body_extra:
            payload.update(body_extra)

        return BuiltRequest(
            method=endpoint.method,
            url=endpoint.url,
            headers=dict(endpoint.headers),
            files=None,
            data=None,
            json=payload,
        )

    def parse_response(self, status_code: int, raw_body: str) -> ParsedResponse:
        ok = 200 <= status_code < 300
        parsed_text = None
        parsed_json = None
        if raw_body:
            try:
                parsed_json = json.loads(raw_body)
                parsed_text = _extract_text_from_openai_body(parsed_json)
            except (json.JSONDecodeError, TypeError):
                if ok:
                    parsed_text = raw_body
        return ParsedResponse(
            ok=ok,
            status=status_code,
            raw_body=raw_body,
            parsed_text=parsed_text,
            parsed_json=parsed_json,
        )
