from __future__ import annotations

from .models import AsrResponse
from ..common import coerce_mapping


def parse_asr_response(response: object) -> AsrResponse:
    payload = coerce_mapping(response, "ASR")
    text = payload.get("text")
    if not isinstance(text, str):
        raise ValueError("ASR response must include a string `text` field.")
    text = text.strip()
    if not text:
        raise ValueError("ASR response text is empty.")
    return AsrResponse(text=text)


def asr_text(response: object) -> str:
    return parse_asr_response(response).text
