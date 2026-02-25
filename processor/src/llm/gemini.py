"""Google Gemini API client via google-genai."""
import logging
from typing import Type

from google import genai

from .. import settings
from . import base

log = logging.getLogger("processor.llm.gemini")


class GeminiClient(base.LLMClient):
    """Client for Google Gemini using the official google-genai package."""

    def __init__(self, model: str | None = None):
        self.model = model or settings.gemini_model()
        api_key = settings.gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required")
        self._client = genai.Client(api_key=api_key)

    def generate(self, system: str, user: str, output_model: Type[base.T]) -> base.T:
        log.info("Using Gemini for structured output | model=%s", self.model)

        config = {
            "system_instruction": system,
            "response_mime_type": "application/json",
            "response_json_schema": output_model.model_json_schema(),
            "max_output_tokens": settings.llm_max_tokens(),
            "temperature": settings.llm_temperature(),
        }
        response = self._client.models.generate_content(
            model=self.model,
            contents=user,
            config=config,
        )
        raw_response = (response.text or "").strip()
        return output_model.model_validate_json(raw_response)
