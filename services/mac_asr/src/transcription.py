from __future__ import annotations

from pathlib import Path

from common.utils.logs import get_logger

from .asr.locale import resolve_locale
from .config.settings import load_settings
from .lang_detect import detect_language

log = get_logger("mac_asr", "transcription")


def resolve_request_locale(path: Path, language: str | None) -> str:
    settings = load_settings()
    explicit_language = (language or "").strip()
    explicit_language_lower = explicit_language.lower()
    log.debug(
        "Resolving ASR request locale | path=%s | language=%s | service_locale=%s",
        path,
        language,
        settings.locale,
    )
    detect_requested = (
        explicit_language_lower == "auto" or settings.locale.strip().lower() == "auto"
    )
    if explicit_language_lower == "auto":
        explicit_language = ""

    detected_code = None
    detected_probability = None
    if not explicit_language and detect_requested:
        detected_code, detected_probability = detect_language(path)
        if detected_probability is None:
            log.debug("No language detected | using default locale=%s", settings.default_locale)
            return resolve_locale(None, settings.default_locale)
        if detected_probability < settings.detect_discard_min_prob:
            log.debug(
                "Discarded ASR language detection | prob=%.3f | min_prob=%.3f",
                detected_probability,
                settings.detect_discard_min_prob,
            )
            return ""
        if detected_probability < settings.detect_default_min_prob:
            log.debug(
                "Using default locale after weak detection | detected=%s | prob=%.3f | min_prob=%.3f",
                detected_code,
                detected_probability,
                settings.detect_default_min_prob,
            )
            return resolve_locale(None, settings.default_locale)
    resolved = resolve_locale(detected_code, explicit_language)
    log.debug(
        "Resolved ASR locale | detected=%s | explicit=%s | resolved=%s",
        detected_code,
        explicit_language or None,
        resolved,
    )
    return resolved


def transcription_text(result: object) -> str:
    text = str(getattr(result, "text", "") or "").strip()
    if not text and hasattr(result, "to_dict"):
        text = str(result.to_dict().get("text", "") or "").strip()
    return text
