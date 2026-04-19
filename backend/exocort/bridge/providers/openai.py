from __future__ import annotations

from ..client import HttpClient
from ..models.asr import AsrRequest, AsrResult
from ..models.ocr import OcrRequest, OcrResult
from ..models.response import ResponseRequest, ResponseResult
from ..utils.media import guess_mime_type, media_to_data_uri, read_media_bytes
from ..utils.provider import split_model_provider
from ..utils.urls import maybe_join_openai_path
from .common import (
    bearer_json_headers,
    compact_strings,
    ensure_text,
    float_to_str,
    response_from_chat_completion,
    require_payload,
    single_page_ocr_result,
)

DEFAULT_OCR_PROMPT = "Extract the readable text from this image. Return only the extracted text."
_ASR_LANGUAGE_CODES = {
    "arabic": "ar",
    "chinese": "zh",
    "dutch": "nl",
    "english": "en",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "japanese": "ja",
    "korean": "ko",
    "portuguese": "pt",
    "russian": "ru",
    "spanish": "es",
}


def _asr_language_code(language: str | None) -> str:
    value = (language or "").strip()
    if not value:
        return ""
    normalized = value.lower().replace("_", "-")
    if normalized in _ASR_LANGUAGE_CODES:
        return _ASR_LANGUAGE_CODES[normalized]
    if "-" in normalized:
        return normalized.split("-", 1)[0]
    return normalized


def asr(
    client: HttpClient,
    api_base: str,
    api_key: str,
    req: AsrRequest,
    extra_headers: dict[str, str],
) -> AsrResult:
    _, model = split_model_provider(req.model)
    url = maybe_join_openai_path(api_base, "/audio/transcriptions")
    headers = {"Authorization": f"Bearer {api_key}", **extra_headers}
    file_name = req.media.file_path.name if req.media.file_path is not None else "audio"
    response = client.post_multipart(
        url,
        headers=headers,
        files={
            "file": (
                file_name,
                read_media_bytes(req.media),
                guess_mime_type(req.media),
            )
        },
        data=compact_strings(
            {
                "model": model,
                "language": _asr_language_code(req.language),
                "prompt": req.prompt or "",
                "temperature": float_to_str(req.temperature),
            }
        ),
    )
    payload = require_payload(response.json, "ASR")
    text = ensure_text(str(payload.get("text", "")), "ASR response text")
    segments = tuple(item for item in payload.get("segments", []) if isinstance(item, dict))
    language = payload.get("language")
    return AsrResult(
        text=text,
        segments=segments,
        language=str(language) if isinstance(language, str) else None,
        raw=payload,
    )


def ocr(
    client: HttpClient,
    api_base: str,
    api_key: str,
    req: OcrRequest,
    extra_headers: dict[str, str],
) -> OcrResult:
    _, model = split_model_provider(req.model)
    prompt = req.prompt or DEFAULT_OCR_PROMPT
    messages = (
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": media_to_data_uri(req.media)}},
            ],
        },
    )
    result = response(
        client,
        api_base,
        api_key,
        ResponseRequest(model=model, messages=messages),
        extra_headers,
    )
    return single_page_ocr_result(result.text, result.raw or {}, "OCR page markdown")


def response(
    client: HttpClient,
    api_base: str,
    api_key: str,
    req: ResponseRequest,
    extra_headers: dict[str, str],
) -> ResponseResult:
    _, model = split_model_provider(req.model)
    url = maybe_join_openai_path(api_base, "/chat/completions")
    headers = bearer_json_headers(api_key, extra_headers)
    payload = {
        "model": model,
        "messages": list(req.messages),
    }
    if req.tools:
        payload["tools"] = list(req.tools)
    if req.tool_choice is not None:
        payload["tool_choice"] = req.tool_choice
    if req.temperature is not None:
        payload["temperature"] = req.temperature
    response_data = client.post_json(url, headers=headers, payload=payload)
    payload_json = require_payload(response_data.json, "response")
    return response_from_chat_completion(payload_json)
