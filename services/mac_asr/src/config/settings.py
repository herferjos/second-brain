from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from common.utils.yaml import load_yaml_config

from .models import MacAsrSettings


def _probability(value: object, default: float) -> float:
    return max(0.0, min(1.0, float(value if value is not None else default)))


@lru_cache(maxsize=1)
def load_settings() -> MacAsrSettings:
    config = load_yaml_config(Path(__file__).resolve().parents[2] / "config.yaml")
    return MacAsrSettings(
        host=str(config.get("host", "127.0.0.1")).strip(),
        port=int(config.get("port", 9092)),
        reload=bool(config.get("reload", True)),
        locale=str(config.get("locale", "auto")).strip(),
        default_locale=str(config.get("default_locale", "es")).strip(),
        transcription_timeout_s=max(3.0, float(config.get("transcription_timeout_s", 30.0))),
        prompt_permission=bool(config.get("prompt_permission", True)),
        log_level=str(config.get("log_level", "info")).lower().strip(),
        detect_model=str(config.get("detect_model", "tiny")).strip(),
        detect_device=str(config.get("detect_device", "cpu")).strip(),
        detect_compute_type=str(config.get("detect_compute_type", "int8")).strip(),
        detect_discard_min_prob=_probability(
            config.get("detect_discard_min_prob", config.get("detect_min_prob")),
            0.5,
        ),
        detect_default_min_prob=_probability(config.get("detect_default_min_prob"), 0.7),
    )
