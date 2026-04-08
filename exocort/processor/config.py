from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class EndpointConfig:
    model: str = ""
    api_base: str = ""
    api_key_env: str = ""


@dataclass(slots=True)
class ProcessingOutputConfig:
    root_path: Path = field(default_factory=lambda: Path("captures") / "processed")


@dataclass(slots=True)
class FileProcessorConfig:
    enabled: bool = False
    watch_dir: Path = field(default_factory=lambda: Path("captures"))
    poll_interval_seconds: int = 5
    output: ProcessingOutputConfig = field(default_factory=ProcessingOutputConfig)
    ocr: EndpointConfig = field(default_factory=EndpointConfig)
    asr: EndpointConfig = field(default_factory=EndpointConfig)
