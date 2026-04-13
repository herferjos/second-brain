from __future__ import annotations

from pathlib import Path

import pytest

from src.config.settings import load_settings


pytestmark = [pytest.mark.service, pytest.mark.unit]


def test_load_settings_reads_yaml() -> None:
    load_settings.cache_clear()

    settings = load_settings()
    assert settings.model_path == "medium"
    assert settings.beam_size == 5
    assert settings.language is None


def test_load_settings_defaults_when_config_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_settings.cache_clear()
    original_exists = Path.exists
    config_path = Path(__file__).resolve().parents[1] / "config.yaml"
    monkeypatch.setattr(
        Path,
        "exists",
        lambda self: False if self == config_path else original_exists(self),
    )

    settings = load_settings()

    assert settings.model_path == "medium"
    assert settings.device == "cpu"
    assert settings.language is None
