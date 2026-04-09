from __future__ import annotations

import os

from dotenv import load_dotenv

from .models import MacOcrSettings


def _str(key: str, default: str) -> str:
    return os.getenv(key, default).strip()


def _int(key: str, default: int) -> int:
    raw = _str(key, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def load_settings() -> MacOcrSettings:
    load_dotenv()
    return MacOcrSettings(
        host=_str("MAC_OCR_HOST", "127.0.0.1"),
        port=_int("MAC_OCR_PORT", 9093),
        log_level=_str("MAC_OCR_LOG_LEVEL", "info").lower(),
    )


__all__ = ["MacOcrSettings", "load_settings"]
