"""Unit tests for exocort.settings."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_log_level_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    from exocort import settings
    assert settings.log_level() == "INFO"


def test_log_level_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    from exocort import settings
    assert settings.log_level() == "DEBUG"


def test_audio_capture_enabled_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUDIO_CAPTURE_ENABLED", raising=False)
    from exocort import settings
    assert settings.audio_capture_enabled() is False


def test_audio_capture_enabled_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_CAPTURE_ENABLED", "1")
    from exocort import settings
    assert settings.audio_capture_enabled() is True


def test_screen_capture_enabled_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCREEN_CAPTURE_ENABLED", raising=False)
    from exocort import settings
    assert settings.screen_capture_enabled() is False


def test_collector_enabled_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COLLECTOR_ENABLED", raising=False)
    from exocort import settings
    assert settings.collector_enabled() is True


def test_collector_enabled_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLLECTOR_ENABLED", "0")
    from exocort import settings
    assert settings.collector_enabled() is False


def test_audio_capture_spool_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUDIO_CAPTURE_SPOOL_DIR", raising=False)
    from exocort import settings
    p = settings.audio_capture_spool_dir()
    assert "tmp" in p.parts and "audio" in p.parts


def test_collector_tmp_dir_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COLLECTOR_TMP_DIR", str(tmp_path / "custom"))
    from exocort import settings
    assert settings.collector_tmp_dir() == tmp_path / "custom"


def test_collector_vault_dir_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COLLECTOR_VAULT_DIR", str(tmp_path / "vault"))
    from exocort import settings
    assert settings.collector_vault_dir() == tmp_path / "vault"
