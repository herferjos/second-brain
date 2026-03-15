"""Single unified engine config: one JSON file for LLM, STT, OCR endpoint specs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import settings
from engine.config import (
    load_json_config,
    normalize_api_format,
    read_dict_str,
    read_float,
    read_int,
    read_list_str,
    read_str,
)
from engine.steps import StepConfig, StepOutputConfig


@dataclass(frozen=True)
class EndpointSpec:
    """Shared HTTP endpoint and auth spec for any task."""

    format: str
    endpoint_url: str
    model: str | None
    api_key: str | None
    api_key_env: str | None
    api_key_header: str | None
    auth_scheme: str
    headers: dict[str, str]
    timeout_s: float
    # custom format only
    custom_request: dict[str, Any] | None
    response_path: str | None


@dataclass(frozen=True)
class LLMSpec:
    endpoint: EndpointSpec
    anthropic_version: str | None
    max_tokens: int
    temperature: float
    max_retries: int
    concurrency: int
    processor_prompts: dict[str, dict[str, str]]


@dataclass(frozen=True)
class SttSpec:
    endpoint: EndpointSpec
    language: str | None
    steps: list[dict]
    output: str


@dataclass(frozen=True)
class OcrSpec:
    endpoint: EndpointSpec
    languages: list[str]
    steps: list[StepConfig]
    output: StepOutputConfig | None


@dataclass(frozen=True)
class EngineConfig:
    llm: LLMSpec
    stt: SttSpec
    ocr: OcrSpec


_engine_config: EngineConfig | None = None


def _read_endpoint(data: dict[str, Any], label: str) -> EndpointSpec:
    raw_format = (read_str(data, "format", None) or "openai").strip().lower()
    format_name = normalize_api_format(raw_format)

    endpoint_url = read_str(data, "endpoint_url", None)
    if format_name not in ("none",) and not endpoint_url:
        raise ValueError(f"{label} config requires 'endpoint_url' when format is not 'none'")

    model = read_str(data, "model", None)
    api_key = read_str(data, "api_key", None)
    api_key_env = read_str(data, "api_key_env", None)
    api_key_header = read_str(data, "api_key_header", None)
    auth_scheme = (read_str(data, "auth_scheme", "bearer") or "bearer").lower()
    headers = read_dict_str(data, "headers")
    timeout_s = read_float(data, "timeout_s", 60.0)

    custom_request = None
    response_path = read_str(data, "response_path", None)
    if format_name == "custom":
        custom_request = data.get("custom_request")
        if isinstance(custom_request, dict):
            pass
        else:
            custom_request = None

    return EndpointSpec(
        format=format_name,
        endpoint_url=endpoint_url or "",
        model=model,
        api_key=api_key,
        api_key_env=api_key_env,
        api_key_header=api_key_header,
        auth_scheme=auth_scheme,
        headers=headers,
        timeout_s=timeout_s,
        custom_request=custom_request,
        response_path=response_path,
    )


def _read_llm(data: dict[str, Any]) -> LLMSpec:
    endpoint = _read_endpoint(data, "LLM")
    anthropic_version = read_str(data, "anthropic_version", None)
    max_tokens = read_int(data, "max_tokens", 4096)
    temperature = read_float(data, "temperature", 0.3)
    max_retries = read_int(data, "max_retries", 3)
    if max_retries < 1:
        max_retries = 1
    concurrency = read_int(data, "concurrency", 1)
    if concurrency < 1:
        concurrency = 1

    prompts_raw = data.get("processor_prompts") or data.get("prompts")
    processor_prompts: dict[str, dict[str, str]] = {}
    if isinstance(prompts_raw, dict):
        for key, value in prompts_raw.items():
            if not isinstance(value, dict):
                continue
            processor_prompts[key] = {
                str(field): str(text)
                for field, text in value.items()
                if isinstance(text, (str, int, float))
            }

    return LLMSpec(
        endpoint=endpoint,
        anthropic_version=anthropic_version,
        max_tokens=max_tokens,
        temperature=temperature,
        max_retries=max_retries,
        concurrency=concurrency,
        processor_prompts=processor_prompts,
    )


def _read_stt(data: dict[str, Any]) -> SttSpec:
    endpoint = _read_endpoint(data, "STT")
    if endpoint.format == "none":
        return SttSpec(
            endpoint=endpoint,
            language=None,
            steps=[],
            output="text",
        )

    language = read_str(data, "language", None)
    steps_raw = data.get("steps") or []
    steps = steps_raw if isinstance(steps_raw, list) else []
    output = read_str(data, "output", "text") or "text"

    return SttSpec(
        endpoint=endpoint,
        language=language,
        steps=steps,
        output=output,
    )


def _read_ocr(data: dict[str, Any]) -> OcrSpec:
    endpoint = _read_endpoint(data, "OCR")
    if endpoint.format == "none":
        return OcrSpec(
            endpoint=endpoint,
            languages=["en", "es"],
            steps=[],
            output=None,
        )

    languages = read_list_str(data, "languages", ["en", "es"])
    if "languages" not in data:
        for key in ("language", "langs", "lang"):
            if key in data:
                languages = read_list_str(data, key, ["en", "es"])
                break

    steps: list[StepConfig] = []
    steps_raw = data.get("steps") or []
    if isinstance(steps_raw, list):
        for idx, raw in enumerate(steps_raw):
            if not isinstance(raw, dict):
                continue
            step_id = (
                read_str(raw, "id", None)
                or read_str(raw, "name", None)
                or f"step_{idx + 1}"
            )
            system_prompt = read_str(raw, "system_prompt", None) or read_str(raw, "system", None)
            user_prompt = (
                read_str(raw, "user_prompt", None)
                or read_str(raw, "prompt", None)
                or read_str(raw, "user", None)
            )
            response = raw.get("response") if isinstance(raw.get("response"), dict) else {}
            response_type = read_str(response, "type", "text") or "text"
            response_path = read_str(response, "path", None) or read_str(response, "field", None)
            temperature = read_float(raw, "temperature", 0.0) if raw.get("temperature") is not None else None
            max_tokens = None
            if raw.get("max_tokens") is not None:
                max_tokens = read_int(raw, "max_tokens", 0)
            elif raw.get("max_output_tokens") is not None:
                max_tokens = read_int(raw, "max_output_tokens", 0)
            steps.append(
                StepConfig(
                    step_id=str(step_id),
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_type=response_type,
                    response_path=response_path,
                    temperature=temperature,
                    max_tokens=max_tokens if max_tokens and max_tokens > 0 else None,
                )
            )

    output_cfg: StepOutputConfig | None = None
    output_raw = data.get("output") if isinstance(data.get("output"), dict) else None
    if output_raw is not None:
        mode = (read_str(output_raw, "mode", "first") or "first").lower()
        output_steps = read_list_str(output_raw, "steps", [])
        raw_separator = output_raw.get("separator")
        separator = raw_separator if isinstance(raw_separator, str) else "\n\n"
        raw_label_format = output_raw.get("label_format")
        label_format = (
            raw_label_format
            if isinstance(raw_label_format, str) and raw_label_format
            else "{id}:\n{value}"
        )
        output_cfg = StepOutputConfig(
            mode=mode,
            steps=output_steps or None,
            separator=separator,
            label_format=label_format,
        )

    return OcrSpec(
        endpoint=endpoint,
        languages=languages,
        steps=steps,
        output=output_cfg,
    )


def load_engine_config(path: Path | None = None) -> EngineConfig:
    p = path or settings.engine_config_path()
    data = load_json_config(p, "Engine")

    llm_raw = data.get("llm")
    if not isinstance(llm_raw, dict):
        raise ValueError("Engine config must have top-level 'llm' object")
    llm = _read_llm(llm_raw)

    stt_raw = data.get("stt")
    if not isinstance(stt_raw, dict):
        raise ValueError("Engine config must have top-level 'stt' object")
    stt = _read_stt(stt_raw)

    ocr_raw = data.get("ocr")
    if not isinstance(ocr_raw, dict):
        raise ValueError("Engine config must have top-level 'ocr' object")
    ocr = _read_ocr(ocr_raw)

    return EngineConfig(llm=llm, stt=stt, ocr=ocr)


def get_engine_config() -> EngineConfig:
    global _engine_config
    if _engine_config is None:
        _engine_config = load_engine_config()
    return _engine_config


def get_processor_prompt(section: str, field: str) -> str:
    cfg = get_engine_config()
    raw = cfg.llm.processor_prompts.get(section, {})
    value = raw.get(field) if isinstance(raw, dict) else None
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, (int, float)):
        return str(value)
    raise ValueError(
        f"Missing processor prompt '{section}.{field}' in engine config. "
        "Define it under 'llm.processor_prompts' in config.json."
    )
