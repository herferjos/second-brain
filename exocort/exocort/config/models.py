from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from exocort.capturer.audio.vad import AudioVADConfig


@dataclass(slots=True, frozen=True)
class AudioSettings:
    enabled: bool = False
    chunk_seconds: int = 30
    sample_rate: int = 16_000
    channels: int = 1
    output_dir: Path = field(default_factory=lambda: Path("captures") / "audio")
    vad: AudioVADConfig = field(default_factory=AudioVADConfig)


@dataclass(slots=True, frozen=True)
class ScreenSettings:
    enabled: bool = False
    interval_seconds: int = 5
    output_dir: Path = field(default_factory=lambda: Path("captures") / "screen")


@dataclass(slots=True, frozen=True)
class EndpointSettings:
    model: str = ""
    api_base: str = ""
    api_key_env: str = ""


@dataclass(slots=True, frozen=True)
class ProcessorSettings:
    enabled: bool = False
    watch_dir: Path = field(default_factory=lambda: Path("captures"))
    output_dir: Path = field(default_factory=lambda: Path("captures") / "processed")
    ocr: EndpointSettings = field(default_factory=EndpointSettings)
    asr: EndpointSettings = field(default_factory=EndpointSettings)


@dataclass(slots=True, frozen=True)
class ExocortSettings:
    audio: AudioSettings = field(default_factory=AudioSettings)
    screen: ScreenSettings = field(default_factory=ScreenSettings)
    processor: ProcessorSettings = field(default_factory=ProcessorSettings)
