"""Load processor LLM configuration from the shared config.json file."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LLMConfig:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppConfig:
    prompts: dict[str, str]
    llm: LLMConfig


def load_app_config(path: Path | None = None) -> AppConfig:
    if path is None:
        from exocort import settings
        path = settings.collector_config_path() # Or a more appropriate default

    if not path.exists():
        raise FileNotFoundError(f"Config file not found at {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    prompts = {
        "l1_clean": os.environ.get("PROMPT_L1_CLEAN", ""),
        "l2_group": os.environ.get("PROMPT_L2_GROUP", ""),
        "l3_user_model": os.environ.get("PROMPT_L3_USER_MODEL", ""),
        "l4_reflection": os.environ.get("PROMPT_L4_REFLECTION", ""),
    }
    prompts = {k: v for k, v in prompts.items() if v}

    llm_data = data.get("llm", {})
    if not isinstance(llm_data, dict):
        llm_data = {}

    headers = {str(k): str(v) for k, v in llm_data.get("headers", {}).items()}
    if "openai_api_key" in os.environ:
        headers.setdefault("Authorization", f"Bearer {os.environ['OPENAI_API_KEY']}")
    elif "gemini_api_key" in os.environ:
        headers.setdefault("x-goog-api-key", os.environ["GEMINI_API_KEY"])


    llm = LLMConfig(
        url=str(llm_data.get("url", "")),
        headers=headers,
        body=llm_data.get("body", {}),
    )

    return AppConfig(prompts=prompts, llm=llm)
