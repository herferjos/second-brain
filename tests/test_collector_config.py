"""Unit tests for collector config loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from exocort.collector.config import CollectorConfig, EndpointConfig


pytestmark = pytest.mark.unit


def test_load_missing_file_returns_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COLLECTOR_CONFIG", str(tmp_path / "nonexistent.json"))
    monkeypatch.chdir(tmp_path)
    cfg = CollectorConfig.load()
    assert cfg.audio == []
    assert cfg.screen == []


def test_load_from_path(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("""{
      "audio": {
        "endpoints": [
          {
            "url": "http://localhost:9092/transcribe",
            "method": "POST",
            "timeout": 15,
            "forward_form": true,
            "headers": {"X-Custom": "yes"}
          }
        ]
      },
      "screen": {
        "endpoints": [
          {"url": "http://localhost:9091/ocr", "timeout": 10}
        ]
      }
    }""")
    cfg = CollectorConfig.load(path=path)
    assert len(cfg.audio) == 1
    assert cfg.audio[0].url == "http://localhost:9092/transcribe"
    assert cfg.audio[0].method == "POST"
    assert cfg.audio[0].timeout == 15.0
    assert cfg.audio[0].forward_form is True
    assert cfg.audio[0].headers == {"X-Custom": "yes"}

    assert len(cfg.screen) == 1
    assert cfg.screen[0].url == "http://localhost:9091/ocr"
    assert cfg.screen[0].method == "POST"
    assert cfg.screen[0].timeout == 10.0
    assert cfg.screen[0].forward_form is True


def test_endpoint_config_defaults() -> None:
    ep = EndpointConfig(url="http://x/y")
    assert ep.method == "POST"
    assert ep.timeout == 30.0
    assert ep.forward_form is True
    assert ep.headers == {}
