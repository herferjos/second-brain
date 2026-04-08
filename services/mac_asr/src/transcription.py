from __future__ import annotations

from pathlib import Path

from . import config
from .asr import resolve_locale
from .lang_detect import detect_language


def resolve_request_locale(path: Path, language: str | None) -> str:
    explicit_language = (language or "").strip()
    explicit_language_lower = explicit_language.lower()
    detect_requested = (
        explicit_language_lower == "auto" or config.LOCALE.strip().lower() == "auto"
    )
    if explicit_language_lower == "auto":
        explicit_language = ""

    detected_code = None
    detected_probability = None
    if not explicit_language and detect_requested:
        detected_code, detected_probability = detect_language(path)
        if detected_probability is None:
            return resolve_locale(None, config.DEFAULT_LOCALE)
        if detected_probability < config.DETECT_DISCARD_MIN_PROB:
            return ""
        if detected_probability < config.DETECT_DEFAULT_MIN_PROB:
            return resolve_locale(None, config.DEFAULT_LOCALE)
    return resolve_locale(detected_code, explicit_language)


def transcription_text(result: object) -> str:
    text = str(getattr(result, "text", "") or "").strip()
    if not text and hasattr(result, "to_dict"):
        text = str(result.to_dict().get("text", "") or "").strip()
    return text
