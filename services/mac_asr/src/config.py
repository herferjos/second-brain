from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str) -> str:
    raw = os.getenv(key)
    return raw.strip() if raw else default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = _env(key, "true" if default else "false").lower()
    return raw in ("1", "true", "yes", "on")


HOST = _env("MAC_ASR_HOST", "127.0.0.1")
PORT = int(_env_float("MAC_ASR_PORT", 9092))
LOCALE = _env("MAC_ASR_LOCALE", "auto")
DEFAULT_LOCALE = _env("MAC_ASR_DEFAULT_LOCALE", "es")
TRANSCRIPTION_TIMEOUT_S = max(3.0, _env_float("MAC_ASR_TRANSCRIPTION_TIMEOUT_S", 30.0))
PROMPT_PERMISSION = _env_bool("MAC_ASR_PROMPT_PERMISSION", True)
LOG_LEVEL = getattr(logging, _env("MAC_ASR_LOG_LEVEL", "INFO").upper(), logging.INFO)

DETECT_MODEL = _env("MAC_ASR_DETECT_MODEL", "tiny")
DETECT_DEVICE = _env("MAC_ASR_DETECT_DEVICE", "cpu")
DETECT_COMPUTE_TYPE = _env("MAC_ASR_DETECT_COMPUTE_TYPE", "int8")
DETECT_DISCARD_MIN_PROB = max(
    0.0,
    min(1.0, _env_float("MAC_ASR_DETECT_DISCARD_MIN_PROB", _env_float("MAC_ASR_DETECT_MIN_PROB", 0.5))),
)
DETECT_DEFAULT_MIN_PROB = max(
    0.0,
    min(1.0, _env_float("MAC_ASR_DETECT_DEFAULT_MIN_PROB", 0.7)),
)
DETECT_MIN_PROB = DETECT_DEFAULT_MIN_PROB

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
