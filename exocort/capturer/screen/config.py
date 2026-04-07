from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ScreenCaptureConfig:
    interval_seconds: int = 5
    output_dir: Path = field(default_factory=lambda: Path("captures") / "screen")
