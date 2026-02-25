import logging
import os
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass
class Transcript:
    text: str
    model: str
    language: str | None = None


def transcribe_audio(path: Path, mime_type: str | None = None) -> Transcript | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    model = (
        os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1").strip() or "whisper-1"
    )
    url = (
        os.getenv(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1/audio/transcriptions",
        ).strip()
        or "https://api.openai.com/v1/audio/transcriptions"
    )

    try:
        content_type = (mime_type or "").strip() or "application/octet-stream"
        with path.open("rb") as f:
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (path.name, f, content_type)},
                data={"model": model},
                timeout=60,
            )
        resp.raise_for_status()
        data = resp.json()
        return Transcript(
            text=(data.get("text") or "").strip(),
            model=model,
            language=data.get("language"),
        )
    except Exception as e:
        logging.getLogger("collector.transcribe").warning(
            "Transcription failed | path=%s | error=%s", path, e
        )
        return None


def transcribe_wav(path: Path) -> Transcript | None:
    # Backwards-compatible name: the audio capture pipeline uploads WAV.
    return transcribe_audio(path, mime_type="audio/wav")
