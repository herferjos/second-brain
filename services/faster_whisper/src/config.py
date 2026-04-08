from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import tomllib

from dotenv import load_dotenv

load_dotenv()


@dataclass
class FasterWhisperSettings:
    host: str
    port: int
    model_path: str
    device: str
    compute_type: str
    beam_size: int
    language: str | None


def load_settings(path: Path | None = None) -> FasterWhisperSettings:
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(path)
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        host = str(data.get("host", "127.0.0.1"))
        port = int(data.get("port", 9000))
        model_path = str(data.get("model_path", "medium"))
        device = str(data.get("device", "cpu"))
        compute_type = str(data.get("compute_type", "int8"))
        beam_size = int(data.get("beam_size", 5))
        language = data.get("language")
    else:
        host = os.environ.get("FASTER_WHISPER_HOST", "127.0.0.1")
        port = int(os.environ.get("FASTER_WHISPER_PORT", 9000))
        model_path = os.environ.get("FASTER_WHISPER_MODEL_PATH", "medium")
        device = os.environ.get("FASTER_WHISPER_DEVICE", "cpu")
        compute_type = os.environ.get("FASTER_WHISPER_COMPUTE_TYPE", "int8")
        beam_size = int(os.environ.get("FASTER_WHISPER_BEAM_SIZE", 5))
        language = os.environ.get("FASTER_WHISPER_LANGUAGE") or None

    if language and language.lower() == "auto":
        language = None

    return FasterWhisperSettings(
        host=host,
        port=port,
        model_path=model_path,
        device=device,
        compute_type=compute_type,
        beam_size=beam_size,
        language=language,
    )


__all__ = ["FasterWhisperSettings", "load_settings"]
