"""Base interfaces for format adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from engine.unified_config import EndpointSpec


class ChatAdapter(ABC):
    """Builds request and parses response for chat-completion-style endpoints."""

    @abstractmethod
    def build_headers(
        self,
        spec: EndpointSpec,
        api_key: str,
        anthropic_version: str | None = None,
    ) -> dict[str, str]:
        pass

    @abstractmethod
    def build_body(
        self,
        spec: EndpointSpec,
        system: str,
        user: str,
        timeout_s: float,
        *,
        model: str | None = None,
        image_path: Path | None = None,
        audio_path: Path | None = None,
        audio_mime_type: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        output_model: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def parse_response(self, payload: dict[str, Any], spec: EndpointSpec | None = None) -> str:
        pass


class TranscriptionAdapter(ABC):
    """Builds request and parses response for transcription (multipart) endpoints."""

    @abstractmethod
    def build_headers(self, spec: EndpointSpec, api_key: str) -> dict[str, str]:
        pass

    @abstractmethod
    def build_form_data(
        self,
        spec: EndpointSpec,
        file_path: Path,
        *,
        model: str | None = None,
        language: str | None = None,
        prompt: str | None = None,
    ) -> tuple[dict[str, str], dict[str, tuple[str, Any, str]]]:
        """Return (data dict for form fields, files dict for file upload)."""
        pass

    @abstractmethod
    def parse_response(self, payload: dict[str, Any], spec: EndpointSpec | None = None) -> str:
        pass
