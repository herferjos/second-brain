from __future__ import annotations

import asyncio
import io

import pytest
from starlette.datastructures import UploadFile

from common.models.asr import TranscriptionRequest, TranscriptionResponse
from services.faster_whisper.app.api.v1.endpoints.transcriptions import transcribe_audio


pytestmark = [pytest.mark.service, pytest.mark.unit]


def test_transcribe_audio_returns_joined_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.faster_whisper.app.api.v1.endpoints.transcriptions.transcribe_path",
        lambda path, language, prompt: TranscriptionResponse(
            text="hello world",
            language=language or "en",
            duration=None,
        ),
    )
    upload = UploadFile(filename="voice.wav", file=io.BytesIO(b"fake-audio"))

    payload = asyncio.run(
        transcribe_audio(
            file=upload,
            payload=TranscriptionRequest(language="en", prompt="test"),
        )
    )

    assert payload.model_dump() == {
        "text": "hello world",
        "task": "transcribe",
        "language": "en",
        "duration": None,
    }
