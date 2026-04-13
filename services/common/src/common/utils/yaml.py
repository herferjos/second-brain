from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml


def load_yaml_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}

    data = yaml.safe_load(config_path.read_text())
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise ValueError(f"{config_path} must contain a YAML mapping at the top level.")
    return dict(data)


def resolve_config_path(base_dir: Path, value: object, default: str) -> Path:
    raw = str(value or default).strip()
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()
