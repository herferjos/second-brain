from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from common.utils.yaml import load_yaml_config

from .models import MacOcrSettings


@lru_cache(maxsize=1)
def load_settings() -> MacOcrSettings:
    config = load_yaml_config(Path(__file__).resolve().parents[2] / "config.yaml")
    return MacOcrSettings(
        host=str(config.get("host", "127.0.0.1")).strip(),
        port=int(config.get("port", 9093)),
        reload=bool(config.get("reload", True)),
        log_level=str(config.get("log_level", "info")).lower().strip(),
    )
