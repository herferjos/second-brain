"""Format adapters for endpoint-agnostic engine: openai, anthropic, custom."""

from .base import ChatAdapter, TranscriptionAdapter
from .openai import OpenAIChatAdapter, OpenAITranscriptionAdapter
from .anthropic import AnthropicChatAdapter
from .custom import CustomChatAdapter, CustomTranscriptionAdapter

_CHAT_ADAPTERS: dict[str, ChatAdapter] = {
    "openai": OpenAIChatAdapter(),
    "anthropic": AnthropicChatAdapter(),
    "custom": CustomChatAdapter(),
}

_TRANSCRIPTION_ADAPTERS: dict[str, TranscriptionAdapter] = {
    "openai": OpenAITranscriptionAdapter(),
    "custom": CustomTranscriptionAdapter(),
}


def get_chat_adapter(format_name: str) -> ChatAdapter:
    name = (format_name or "openai").strip().lower()
    if name not in _CHAT_ADAPTERS:
        raise ValueError(f"Unsupported chat format: {name!r}. Use one of: openai, anthropic, custom.")
    return _CHAT_ADAPTERS[name]


def get_transcription_adapter(format_name: str) -> TranscriptionAdapter:
    name = (format_name or "openai").strip().lower()
    if name not in _TRANSCRIPTION_ADAPTERS:
        raise ValueError(f"Unsupported transcription format: {name!r}. Use one of: openai, custom.")
    return _TRANSCRIPTION_ADAPTERS[name]
