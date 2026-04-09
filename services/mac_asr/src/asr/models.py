from __future__ import annotations

from dataclasses import dataclass

from common.models.asr import TranscriptionRequest, TranscriptionResponse


@dataclass(frozen=True)
class Transcription:
    text: str


__all__ = ["Transcription", "TranscriptionRequest", "TranscriptionResponse"]
