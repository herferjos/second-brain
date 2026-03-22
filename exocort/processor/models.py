"""Shared processor dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


ExecutionMode = Literal["per_stage_worker", "single_loop"]
StageType = Literal["llm_map", "llm_reduce", "deterministic_map", "deterministic_reduce", "noop"]
ProjectionType = Literal["none", "jsonl_day", "markdown_note"]
BaseDirType = Literal["vault", "out", "state"]


@dataclass(frozen=True)
class CollectionDefinition:
    path: str
    base_dir: BaseDirType
    format: str


@dataclass
class OutputDefinition:
    name: str
    collection: CollectionDefinition
    projection: ProjectionType
    result_key: str
    kind: str
    id_field: str
    date_field: str
    timestamp_field: str
    source_id_field: str | None = None
    projection_target: CollectionDefinition | None = None

    def __post_init__(self) -> None:
        if isinstance(self.collection, dict):
            self.collection = CollectionDefinition(**self.collection)
        if isinstance(self.projection_target, dict):
            self.projection_target = CollectionDefinition(**self.projection_target)


@dataclass
class StageDefinition:
    name: str
    type: StageType
    input: CollectionDefinition
    outputs: list[OutputDefinition]
    enabled: bool
    state_key: str
    prompt: str | None
    batch_size: int
    flush_threshold: int
    flush_when_upstream_empty: bool
    upstream: list[CollectionDefinition]
    archive: CollectionDefinition | None
    transform_adapter: str
    transform_options: dict[str, Any]
    concurrency: int

    def __post_init__(self) -> None:
        if isinstance(self.input, dict):
            self.input = CollectionDefinition(**self.input)
        if isinstance(self.archive, dict):
            self.archive = CollectionDefinition(**self.archive)
        self.upstream = [
            item if isinstance(item, CollectionDefinition) else CollectionDefinition(**item)
            for item in self.upstream
        ]
        self.batch_size = int(self.batch_size)
        self.flush_threshold = int(self.flush_threshold)
        self.concurrency = int(self.concurrency)
        if self.batch_size < 1:
            raise ValueError(f"Stage {self.name} batch_size must be >= 1")
        if self.flush_threshold < 1:
            raise ValueError(f"Stage {self.name} flush_threshold must be >= 1")
        if self.concurrency < 1:
            raise ValueError(f"Stage {self.name} concurrency must be >= 1")
        self.outputs = [
            item if isinstance(item, OutputDefinition) else OutputDefinition(**item)
            for item in self.outputs
        ]
        self.prompt = str(self.prompt).strip() if self.prompt is not None else None


@dataclass
class PipelineDefinition:
    execution_mode: ExecutionMode
    stages: list[StageDefinition]

    def __post_init__(self) -> None:
        self.stages = [
            item if isinstance(item, StageDefinition) else StageDefinition(**item)
            for item in self.stages
        ]


@dataclass
class ArtifactEnvelope:
    kind: str
    stage: str
    item_id: str
    date: str
    payload: dict[str, Any]
    timestamp: str = ""
    source_ids: list[str] = field(default_factory=list)
    source_paths: list[str] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "stage": self.stage,
            "item_id": self.item_id,
            "timestamp": self.timestamp,
            "date": self.date,
            "source_ids": list(self.source_ids),
            "source_paths": list(self.source_paths),
            "trace": dict(self.trace),
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactEnvelope":
        payload = data.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("Artifact payload must be a JSON object")
        source_ids = data.get("source_ids")
        source_paths = data.get("source_paths")
        trace = data.get("trace")
        return cls(
            kind=str(data["kind"]),
            stage=str(data["stage"]),
            item_id=str(data["item_id"]),
            timestamp=str(data.get("timestamp") or ""),
            date=str(data["date"]),
            source_ids=[str(value).strip() for value in source_ids if str(value).strip()] if isinstance(source_ids, list) else [],
            source_paths=[str(value).strip() for value in source_paths if str(value).strip()] if isinstance(source_paths, list) else [],
            trace=trace if isinstance(trace, dict) else {},
            payload=payload,
        )


@dataclass
class ProcessorState:
    cursor_path: str | None = None
    cursor_id: str | None = None
    last_output_path: str | None = None
    last_output_id: str | None = None
    last_run_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cursor_path": self.cursor_path,
            "cursor_id": self.cursor_id,
            "last_output_path": self.last_output_path,
            "last_output_id": self.last_output_id,
            "last_run_at": self.last_run_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProcessorState":
        metadata = data.get("metadata")
        return cls(
            cursor_path=str(data["cursor_path"]) if data.get("cursor_path") is not None else None,
            cursor_id=str(data["cursor_id"]) if data.get("cursor_id") is not None else None,
            last_output_path=str(data["last_output_path"]) if data.get("last_output_path") is not None else None,
            last_output_id=str(data["last_output_id"]) if data.get("last_output_id") is not None else None,
            last_run_at=str(data["last_run_at"]) if data.get("last_run_at") is not None else None,
            metadata=metadata if isinstance(metadata, dict) else {},
        )


@dataclass
class ProcessorConfig:
    vault_dir: Path
    out_dir: Path
    state_dir: Path
    poll_interval_s: float
    max_concurrent_tasks: int
    dry_run: bool
    pipeline: PipelineDefinition

    def __post_init__(self) -> None:
        self.vault_dir = Path(self.vault_dir)
        self.out_dir = Path(self.out_dir)
        self.state_dir = Path(self.state_dir)
        self.poll_interval_s = float(self.poll_interval_s)
        self.max_concurrent_tasks = int(self.max_concurrent_tasks)
        if self.poll_interval_s <= 0:
            raise ValueError("Processor poll_interval_s must be > 0")
        if self.max_concurrent_tasks < 1:
            raise ValueError("Processor max_concurrent_tasks must be >= 1")

    @property
    def execution_mode(self) -> ExecutionMode:
        return self.pipeline.execution_mode

    @property
    def stages(self) -> list[StageDefinition]:
        return [stage for stage in self.pipeline.stages if stage.enabled]
