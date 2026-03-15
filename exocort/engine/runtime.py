"""Single endpoint-agnostic runtime for LLM, OCR and STT over HTTP."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Type, TypeVar

from pydantic import BaseModel

from . import http
from engine.base import LLMClient
from engine.config import resolve_api_key
from engine.steps import StepConfig, extract_json_path, format_step_outputs, render_prompt
from engine.unified_config import get_engine_config, get_processor_prompt

log = logging.getLogger("engine.runtime")

T = TypeVar("T", bound=BaseModel)

_runtime: "EngineRuntime | None" = None


def _is_retriable(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "503" in msg or "500" in msg


def _with_retry(fn: Callable[[], T], max_retries: int = 3) -> T:
    last: BaseException | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except BaseException as exc:
            last = exc
            if attempt < max_retries - 1 and _is_retriable(exc):
                delay = 2**attempt
                log.warning("LLM call failed, retrying in %ds: %s", delay, exc)
                time.sleep(delay)
                continue
            raise
    if last is not None:
        raise last
    raise RuntimeError("Max retries exceeded")


class EngineRuntime(LLMClient):
    """One runtime object for all engine capabilities."""

    def generate(self, system: str, user: str, output_model: Type[T]) -> T:
        cfg = get_engine_config().llm
        spec = cfg.endpoint
        api_key = resolve_api_key(spec.api_key, spec.api_key_env, None)
        if spec.format in {"openai", "anthropic"} and not api_key:
            raise ValueError("LLM config requires an API key via 'api_key' or 'api_key_env'")

        def run() -> T:
            text = http.chat_completion(
                spec=spec,
                api_key=api_key,
                anthropic_version=cfg.anthropic_version,
                system=system,
                user=user,
                timeout_s=spec.timeout_s,
                model=spec.model,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                output_model=output_model,
            )
            return http.parse_structured_output(text, output_model)

        return _with_retry(run, max_retries=cfg.max_retries)

    def transcribe(self, path: Path, mime_type: str | None = None) -> str:
        cfg = get_engine_config().stt
        spec = cfg.endpoint
        if spec.format == "none" or not spec.endpoint_url:
            return ""
        api_key = resolve_api_key(spec.api_key, spec.api_key_env, None)
        return http.transcription(
            spec=spec,
            api_key=api_key,
            file_path=path,
            timeout_s=spec.timeout_s,
            model=spec.model,
            language=cfg.language,
            prompt=None,
        )

    def extract_text(self, path: Path) -> str:
        cfg = get_engine_config().ocr
        spec = cfg.endpoint
        if spec.format == "none" or not spec.endpoint_url:
            return ""

        if not cfg.steps:
            dummy_step = StepConfig(
                step_id="ocr",
                system_prompt="You are an OCR engine. Extract plain text from the image.",
                user_prompt="Read the text in the image and return it as plain text.",
                response_type="text",
                response_path=None,
                temperature=None,
                max_tokens=None,
            )
            return self._run_ocr_step(spec, dummy_step, path, {})

        results: list[tuple[str, str]] = []
        context: dict[str, str] = {}
        for step in cfg.steps:
            text = self._run_ocr_step(spec, step, path, context)
            results.append((step.step_id, text))
            context["prev"] = text
            context[step.step_id] = text
        return format_step_outputs(results, cfg.output)

    def llm_concurrency(self) -> int:
        return get_engine_config().llm.concurrency

    def _run_ocr_step(
        self,
        spec,
        step: StepConfig,
        image_path: Path,
        context: dict[str, str],
    ) -> str:
        api_key = resolve_api_key(spec.api_key, spec.api_key_env, None)
        if spec.format in {"openai", "anthropic"} and not api_key:
            raise ValueError("OCR config requires an API key via 'api_key' or 'api_key_env'")

        llm = get_engine_config().llm
        system_prompt = render_prompt(step.system_prompt, context).strip() if step.system_prompt else ""
        user_prompt = render_prompt(step.user_prompt, context).strip() if step.user_prompt else ""
        text = http.chat_completion(
            spec=spec,
            api_key=api_key,
            anthropic_version=llm.anthropic_version if spec.format == "anthropic" else None,
            system=system_prompt,
            user=user_prompt,
            timeout_s=spec.timeout_s,
            model=spec.model,
            image_path=image_path,
            temperature=step.temperature,
            max_tokens=step.max_tokens,
        )

        if (step.response_type or "").lower() != "json":
            return text
        try:
            import json
            payload = json.loads(text)
        except Exception:
            return text
        extracted = extract_json_path(payload, step.response_path)
        if extracted is None:
            return text
        if isinstance(extracted, str):
            return extracted.strip()
        import json as _json
        return _json.dumps(extracted, ensure_ascii=False)


def get_runtime() -> EngineRuntime:
    global _runtime
    if _runtime is None:
        _runtime = EngineRuntime()
    return _runtime


__all__ = ["EngineRuntime", "get_runtime", "get_processor_prompt"]
