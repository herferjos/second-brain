"""Load processor LLM configuration from the shared config.json file."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LLMServiceConfig:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)

@dataclass
class AppConfig:
    prompts: dict[str, str]
    llm_service: LLMServiceConfig

def load_app_config(path: Path | None = None) -> AppConfig:
    if path is None:
        from exocort import settings
        path = settings.collector_config_path() # Or a more appropriate default

    if not path.exists():
        raise FileNotFoundError(f"Config file not found at {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    prompts = data.get("prompts", {})
    if not isinstance(prompts, dict):
        prompts = {}

    llm_service_data = data.get("llm_service", {})
    if not isinstance(llm_service_data, dict):
        llm_service_data = {}

    llm_service = LLMServiceConfig(
        url=str(llm_service_data.get("url", "")),
        headers={str(k): str(v) for k, v in llm_service_data.get("headers", {}).items()},
        body=llm_service_data.get("body", {}),
    )

    return AppConfig(prompts=prompts, llm_service=llm_service)