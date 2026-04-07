from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import tomllib

from exocort.capturer.audio.config import AudioCaptureConfig
from exocort.capturer.screen.config import ScreenCaptureConfig


@dataclass(slots=True)
class AudioRunnerConfig:
    enabled: bool = False
    chunk_seconds: int = 30
    sample_rate: int = 16_000
    channels: int = 1


@dataclass(slots=True)
class ScreenRunnerConfig:
    enabled: bool = False
    interval_seconds: int = 5


@dataclass(slots=True)
class CaptureOutputConfig:
    root_path: Path = Path("captures")

    @property
    def audio_dir(self) -> Path:
        return self.root_path / "audio"

    @property
    def screen_dir(self) -> Path:
        return self.root_path / "screen"


@dataclass(slots=True)
class ExocortConfig:
    capture: CaptureOutputConfig = field(default_factory=CaptureOutputConfig)
    audio: AudioRunnerConfig = field(default_factory=AudioRunnerConfig)
    screen: ScreenRunnerConfig = field(default_factory=ScreenRunnerConfig)

    @property
    def audio_capture(self) -> AudioCaptureConfig:
        return AudioCaptureConfig(
            chunk_seconds=self.audio.chunk_seconds,
            sample_rate=self.audio.sample_rate,
            channels=self.audio.channels,
            output_dir=self.capture.audio_dir,
        )

    @property
    def screen_capture(self) -> ScreenCaptureConfig:
        return ScreenCaptureConfig(
            interval_seconds=self.screen.interval_seconds,
            output_dir=self.capture.screen_dir,
        )


def load_config(path: str | Path) -> ExocortConfig:
    config_path = Path(path)
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return parse_config(raw)


def parse_config(raw: dict[str, Any], base_dir: Path | None = None) -> ExocortConfig:
    base_dir = base_dir or Path.cwd()
    capturer_raw = _get_table(raw, "capturer")
    audio_raw = _get_table(capturer_raw, "audio")
    screen_raw = _get_table(capturer_raw, "screen")

    capture_root = _resolve_path(
        capturer_raw.get("path"),
        base_dir,
        base_dir / "captures",
    )

    return ExocortConfig(
        capture=CaptureOutputConfig(root_path=capture_root),
        audio=AudioRunnerConfig(
            enabled=bool(audio_raw.get("enabled", False)),
            chunk_seconds=int(audio_raw.get("chunk_seconds", AudioCaptureConfig.chunk_seconds)),
            sample_rate=int(audio_raw.get("sample_rate", AudioCaptureConfig.sample_rate)),
            channels=int(audio_raw.get("channels", AudioCaptureConfig.channels)),
        ),
        screen=ScreenRunnerConfig(
            enabled=bool(screen_raw.get("enabled", False)),
            interval_seconds=int(
                screen_raw.get("interval_seconds", ScreenCaptureConfig.interval_seconds)
            )
        ),
    )


def _get_table(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{key}' must be a table/object.")
    return value


def _resolve_path(value: Any | None, base_dir: Path, default: Path) -> Path:
    if value is None:
        resolved = default
    else:
        resolved = Path(value)
        if not resolved.is_absolute():
            resolved = base_dir / resolved
    return resolved.expanduser()
