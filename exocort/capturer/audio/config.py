from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class AudioCaptureConfig:
    chunk_seconds: int = 30
    sample_rate: int = 16_000
    channels: int = 1
    output_dir: Path = field(default_factory=lambda: Path("captures") / "audio")
