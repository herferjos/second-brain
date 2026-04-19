from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def coerce_mapping(value: object, label: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    if hasattr(value, "dict"):
        dumped = value.dict()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    if isinstance(value, (str, bytes, bytearray)):
        loaded = json.loads(value)
        if isinstance(loaded, Mapping):
            return dict(loaded)
    raise ValueError(f"{label} response has an unsupported shape.")
