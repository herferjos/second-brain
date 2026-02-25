"""OpenAI API client using the official openai library."""
import logging
from typing import Type

from openai import OpenAI

from .. import settings
from . import base

log = logging.getLogger("processor.llm.openai")


class OpenAIClient(base.LLMClient):
    """Client for OpenAI chat completions with structured output via Pydantic."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = base_url or settings.openai_base_url()
        self.model = model or settings.openai_model()
        self.api_key = getattr(settings, "api_key", None) or settings.openai_api_key()
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    def generate(self, system: str, user: str, output_model: Type[base.T]) -> base.T:
        log.info("Using OpenAI for structured output | model=%s", self.model)

        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text_format=output_model,
            max_output_tokens=settings.llm_max_tokens(),
            temperature=settings.llm_temperature(),
        )
        return response.output_parsed
