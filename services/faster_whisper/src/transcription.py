from __future__ import annotations

from pathlib import Path

from src.config import FasterWhisperSettings, load_settings


def _create_model(settings: FasterWhisperSettings):
    from faster_whisper import WhisperModel

    return WhisperModel(
        settings.model_path,
        device=settings.device,
        compute_type=settings.compute_type,
    )


settings = load_settings()
model = None


def get_model():
    global model
    if model is None:
        model = _create_model(settings)
    return model


def transcribe_path(
    path: Path,
    *,
    language: str | None,
    prompt: str | None,
) -> dict[str, object] | None:
    segments, _info = get_model().transcribe(
        str(path),
        beam_size=settings.beam_size,
        language=language or settings.language,
        initial_prompt=prompt or None,
    )

    text_parts: list[str] = [segment.text.strip() for segment in segments if segment.text]
    text = " ".join(text_parts).strip()
    if not text:
        return None
    return {
        "text": text,
        "task": "transcribe",
        "language": language or settings.language,
        "duration": None,
    }


__all__ = ["get_model", "settings", "transcribe_path"]
