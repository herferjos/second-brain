"""Local GGUF model via llama-cpp-python (in-process)."""
import logging
import os
import threading
from typing import Type

from pydantic import BaseModel

from .. import settings
from . import base
from llama_cpp import Llama, LlamaGrammar
from llama_cpp_agent.gbnf_grammar_generator.gbnf_grammar_from_pydantic_models import (
    generate_gbnf_grammar_and_documentation,
)

log = logging.getLogger("processor.llm.localllama")

_model = None
_model_lock = threading.Lock()


def _grammar_and_docs_from_pydantic(model: Type[BaseModel]) -> tuple[LlamaGrammar, str]:
    """Build LlamaGrammar and documentation from a Pydantic model using GBNF."""
    gbnf_grammar, documentation = generate_gbnf_grammar_and_documentation([model])
    grammar = LlamaGrammar.from_string(gbnf_grammar, verbose=False)
    return grammar, documentation


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        model_path = settings.llm_model_path()
        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(
                f"LLM model file not found: {model_path}. Set LLM_MODEL_PATH to your .gguf path."
            )

        log.info(
            "Loading local GGUF model | path=%s | ctx=%d | gpu_layers=%d | threads=%d | batch=%d",
            model_path,
            settings.llm_context_length(),
            settings.llm_n_gpu_layers(),
            settings.llm_threads(),
            settings.llm_batch_size(),
        )

        llama_kwargs = {
            "model_path": model_path,
            "n_ctx": settings.llm_context_length(),
            "n_threads": settings.llm_threads(),
            "n_gpu_layers": settings.llm_n_gpu_layers(),
            "n_batch": settings.llm_batch_size(),
            "use_mmap": settings.llm_use_mmap(),
            "verbose": False,
        }
        if settings.llm_seed() is not None:
            llama_kwargs["seed"] = settings.llm_seed()

        if hasattr(Llama, "flash_attn"):
            llama_kwargs["flash_attn"] = settings.llm_flash_attention()
        if hasattr(Llama, "offload_kqv"):
            llama_kwargs["offload_kqv"] = settings.llm_offload_kqv()

        _model = Llama(**llama_kwargs)
        log.info("Local GGUF model loaded")
        return _model


class LocalLlamaClient(base.LLMClient):
    """Client using llama-cpp-python with a local .gguf file."""

    def generate(self, system: str, user: str, output_model: Type[base.T]) -> base.T:
        model = _get_model()
        log.info("Using local GGUF model for structured generation")

        grammar, documentation = _grammar_and_docs_from_pydantic(output_model)
        system_with_docs = f"{system}\n\n{documentation}"
        messages = [
            {"role": "system", "content": system_with_docs},
            {"role": "user", "content": user},
        ]

        out = model.create_chat_completion(
            messages=messages,
            temperature=settings.llm_temperature(),
            max_tokens=settings.llm_max_tokens(),
            grammar=grammar,
        )
        choice = (out.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content", "")

        try:
            return output_model.model_validate_json(content)
        except Exception as e:
            log.error("Failed to validate structured output from local model: %s", e)
            log.error("Raw model output: %s", content)
            raise
