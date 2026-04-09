from __future__ import annotations

from typing import Literal

from fastapi import Form
from pydantic import BaseModel


class TranscriptionRequest(BaseModel):
    model: str | None = None
    language: str | None = None
    prompt: str | None = None
    response_format: str | None = None
    temperature: float | None = None

    @classmethod
    def as_form(
        cls,
        model: str | None = Form(None),
        language: str | None = Form(None),
        prompt: str | None = Form(None),
        response_format: str | None = Form(None),
        temperature: float | None = Form(None),
    ) -> "TranscriptionRequest":
        return cls(
            model=model,
            language=language,
            prompt=prompt,
            response_format=response_format,
            temperature=temperature,
        )


class TranscriptionResponse(BaseModel):
    text: str
    task: Literal["transcribe"] = "transcribe"
    language: str
    duration: float | None = None


__all__ = ["TranscriptionRequest", "TranscriptionResponse"]
