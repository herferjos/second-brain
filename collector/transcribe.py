import logging
import os
from pathlib import Path

from faster_whisper import WhisperModel

from .openai_transcribe import Transcript, transcribe_audio as transcribe_openai_audio

_FW_MODEL = None
_FW_MODEL_KEY = None


def _env(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    s = raw.strip()
    return s if s else default


def _get_backend() -> str:
    backend = _env("COLLECTOR_TRANSCRIBE_BACKEND", "").lower()
    if backend:
        return backend
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"
    return "none"


def _get_faster_whisper_model():
    global _FW_MODEL, _FW_MODEL_KEY

    model_name = _env("FASTER_WHISPER_MODEL", "small")
    device = _env("FASTER_WHISPER_DEVICE", "cpu")
    compute_type = _env("FASTER_WHISPER_COMPUTE_TYPE", "int8")
    key = f"{model_name}|{device}|{compute_type}"

    if _FW_MODEL is not None and _FW_MODEL_KEY == key:
        return _FW_MODEL

    _FW_MODEL = WhisperModel(model_name, device=device, compute_type=compute_type)
    _FW_MODEL_KEY = key
    return _FW_MODEL


def transcribe_file(path: Path, mime_type: str | None = None) -> Transcript | None:
    """
    Transcribe an audio file using the configured backend.

    Backends:
    - openai: uses OpenAI transcriptions API (requires OPENAI_API_KEY)
    - faster_whisper: local faster-whisper (requires ffmpeg installed)
    - none: no transcription
    """
    backend = _get_backend()
    if backend == "none":
        return None

    if backend == "openai":
        return transcribe_openai_audio(path, mime_type=mime_type)

    if backend == "faster_whisper":
        logger = logging.getLogger("collector.transcribe")
        try:
            model = _get_faster_whisper_model()
            language = _env("FASTER_WHISPER_LANGUAGE", "").strip() or None
            task = _env("FASTER_WHISPER_TASK", "transcribe")
            segments, info = model.transcribe(
                str(path),
                language=language,
                task=task,
                vad_filter=_env("FASTER_WHISPER_VAD_FILTER", "1").lower()
                in {"1", "true", "yes", "on"},
            )
            text = "".join((seg.text or "") for seg in segments).strip()
            if not text:
                return None
            return Transcript(
                text=text,
                model=_env("FASTER_WHISPER_MODEL", "small"),
                language=(getattr(info, "language", None) or None),
            )
        except Exception as e:
            logger.warning("Local transcription failed | path=%s | error=%s", path, e)
            return None

    # Unknown backend -> behave like none.
    return None

