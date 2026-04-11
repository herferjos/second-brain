from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass(slots=True, frozen=True)
class ProcessedArtifact:
    artifact_id: str
    source_kind: Literal["asr", "ocr"]
    json_path: Path
    source_file: Path | None
    source_relpath: str | None
    captured_at: datetime
    text: str


@dataclass(slots=True, frozen=True)
class BatchCandidate:
    artifacts: tuple[ProcessedArtifact, ...]
    input_text: str
    input_tokens: int


@dataclass(slots=True, frozen=True)
class ToolCallResult:
    tool_name: str
    summary: str
    note_path: str | None = None


@dataclass(slots=True, frozen=True)
class BatchRunResult:
    assistant_message: str
    tool_results: tuple[ToolCallResult, ...] = field(default_factory=tuple)
