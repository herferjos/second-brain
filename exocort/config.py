from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import tomllib

from exocort.capturer.audio.config import AudioCaptureConfig
from exocort.capturer.audio.vad import AudioVADConfig
from exocort.capturer.screen.config import ScreenCaptureConfig
from exocort.processor import EndpointConfig, FileProcessorConfig, ProcessingOutputConfig


@dataclass(slots=True)
class AudioRunnerConfig:
    enabled: bool = False
    chunk_seconds: int = 30
    sample_rate: int = 16_000
    channels: int = 1
    vad: AudioVADConfig = field(default_factory=AudioVADConfig)


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
    processor: FileProcessorConfig = field(default_factory=FileProcessorConfig)

    @property
    def audio_capture(self) -> AudioCaptureConfig:
        return AudioCaptureConfig(
            chunk_seconds=self.audio.chunk_seconds,
            sample_rate=self.audio.sample_rate,
            channels=self.audio.channels,
            output_dir=self.capture.audio_dir,
            vad=self.audio.vad,
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
    vad_raw = _get_table(audio_raw, "vad")
    screen_raw = _get_table(capturer_raw, "screen")
    processor_raw = _get_table(raw, "processor")
    processor_output_raw = _get_table(processor_raw, "output")
    processor_ocr_raw = _get_table(processor_raw, "ocr")
    processor_asr_raw = _get_table(processor_raw, "asr")

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
            vad=AudioVADConfig(
                enabled=bool(vad_raw.get("enabled", AudioVADConfig.enabled)),
                energy_threshold=float(
                    vad_raw.get("energy_threshold", AudioVADConfig.energy_threshold)
                ),
                window_seconds=float(vad_raw.get("window_seconds", AudioVADConfig.window_seconds)),
                speech_ratio=float(vad_raw.get("speech_ratio", AudioVADConfig.speech_ratio)),
            ),
        ),
        screen=ScreenRunnerConfig(
            enabled=bool(screen_raw.get("enabled", False)),
            interval_seconds=int(
                screen_raw.get("interval_seconds", ScreenCaptureConfig.interval_seconds)
            )
        ),
        processor=FileProcessorConfig(
            enabled=bool(processor_raw.get("enabled", False)),
            watch_dir=_resolve_path(
                processor_raw.get("watch_dir"),
                base_dir,
                capture_root,
            ),
            poll_interval_seconds=int(
                processor_raw.get("poll_interval_seconds", FileProcessorConfig.poll_interval_seconds)
            ),
            output=ProcessingOutputConfig(
                root_path=_resolve_path(
                    processor_output_raw.get("path"),
                    base_dir,
                    capture_root / "processed",
                )
            ),
            ocr=EndpointConfig(
                model=str(processor_ocr_raw.get("model", "")),
                api_base=str(processor_ocr_raw.get("api_base", "")),
                api_key_env=str(processor_ocr_raw.get("api_key_env", "")),
            ),
            asr=EndpointConfig(
                model=str(processor_asr_raw.get("model", "")),
                api_base=str(processor_asr_raw.get("api_base", "")),
                api_key_env=str(processor_asr_raw.get("api_key_env", "")),
            ),
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
