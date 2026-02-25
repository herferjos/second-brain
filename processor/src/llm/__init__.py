"""Pluggable LLM clients: local GGUF (llama-cpp-python), OpenAI, Gemini."""
import logging

from .. import settings
from . import base
from . import gemini
from . import localllama
from . import openai
from . import retry

log = logging.getLogger("processor.llm")


def get_client(provider: str | None = None) -> base.LLMClient:
    """Return LLM client for the given provider (from env if None), wrapped with retry."""
    p = (provider or settings.llm_provider()).lower()
    if p == "llama_cpp":
        client = localllama.LocalLlamaClient()
    elif p == "openai":
        client = openai.OpenAIClient()
    elif p == "gemini":
        client = gemini.GeminiClient()
    else:
        raise ValueError(f"Unknown LLM provider: {p}")
    return retry.RetryingLLMClient(client, max_retries=settings.llm_max_retries())
