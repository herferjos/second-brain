"""Unit tests for processor config loading from shared TOML."""

from __future__ import annotations

from pathlib import Path

import pytest

from exocort.processor.config import load_app_config, load_processor_config
from exocort.processor.engine import build_worker_specs, validate_pipeline
from exocort.processor.models import PipelineDefinition, ProcessorConfig, StageDefinition


pytestmark = pytest.mark.unit


def _processor_pipeline() -> PipelineDefinition:
    return PipelineDefinition(
        execution_mode="single_loop",
        stages=[
            StageDefinition(
                name="l1",
                type="llm_map",
                input={"base_dir": "vault", "path": ".", "format": "json"},
                outputs=[
                    {
                        "name": "events",
                        "collection": {"base_dir": "out", "path": "events", "format": "json"},
                        "projection": "none",
                        "result_key": "events",
                        "kind": "event",
                        "id_field": "event_id",
                        "date_field": "date",
                        "timestamp_field": "timestamp",
                        "source_id_field": "source_raw_event_id",
                    }
                ],
                enabled=True,
                state_key="raw_to_events",
                prompt="Clean event prompt",
                batch_size=4,
                flush_threshold=2,
                flush_when_upstream_empty=True,
                upstream=[],
                archive=None,
                transform_adapter="llm_map",
                transform_options={"input_mode": "raw", "input_key": "events"},
                concurrency=1,
            )
        ],
    )


def test_load_app_config_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "exocort.toml"
    path.write_text(
        """
[processor]
vault_dir = "vault"
out_dir = "out"
state_dir = "state"
poll_interval_seconds = 3
execution_mode = "single_loop"
max_concurrent_tasks = 2
dry_run = false

[[processor.stages]]
name = "summaries"
enabled = true
type = "llm_reduce"
input = { base_dir = "out", path = "events", format = "json" }
state_key = "summaries"
prompt = "Summarize the events"
batch_size = 1
flush_threshold = 1
flush_when_upstream_empty = true
upstream = []
transform_adapter = "llm_reduce"
transform_options = { input_mode = "payload", input_key = "events" }
concurrency = 1
outputs = [
  { name = "summaries", collection = { base_dir = "out", path = "summaries", format = "json" }, projection = "none", result_key = "items", kind = "summary", id_field = "id", date_field = "date", timestamp_field = "timestamp", source_id_field = "source_ids" },
]

[services.processor]
url = "http://localhost:9100/v1/chat/completions"
headers = { Authorization = "Bearer test-key" }
body = { model = "gpt-4o-mini" }
""",
        encoding="utf-8",
    )

    config = load_app_config(path)

    assert config.llm.url == "http://localhost:9100/v1/chat/completions"
    assert config.llm.headers == {"Authorization": "Bearer test-key"}
    assert config.llm.body == {"model": "gpt-4o-mini"}


def test_load_processor_config_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "exocort.toml"
    path.write_text(
        """
[processor]
vault_dir = "vault"
out_dir = "processed"
state_dir = "state"
execution_mode = "single_loop"
poll_interval_seconds = 3
max_concurrent_tasks = 2
dry_run = false

[[processor.stages]]
name = "l1"
enabled = true
type = "llm_map"
input = { base_dir = "vault", path = ".", format = "json" }
state_key = "raw_to_events"
prompt = "Clean event prompt"
batch_size = 4
flush_threshold = 2
flush_when_upstream_empty = true
upstream = []
transform_adapter = "llm_map"
transform_options = { input_mode = "raw", input_key = "events" }
concurrency = 1
outputs = [
  { name = "events", collection = { base_dir = "out", path = "events", format = "json" }, projection = "none", result_key = "events", kind = "event", id_field = "event_id", date_field = "date", timestamp_field = "timestamp", source_id_field = "source_raw_event_id" },
]

[services.processor]
url = "http://localhost:9100/v1/chat/completions"
headers = {}
body = { model = "gpt-4o-mini" }
""",
        encoding="utf-8",
    )

    config = load_processor_config(path)

    assert config.execution_mode == "single_loop"
    assert config.max_concurrent_tasks == 2
    assert config.poll_interval_s == 3
    assert config.stages[0].input.path == "."
    assert config.stages[0].outputs[0].collection.path == "events"
    assert config.stages[0].state_key == "raw_to_events"
    assert config.stages[0].prompt == "Clean event prompt"
    assert config.stages[0].batch_size == 4


def test_validate_pipeline_rejects_invalid_configs(tmp_path: Path) -> None:
    config = ProcessorConfig(
        vault_dir=tmp_path / "vault",
        out_dir=tmp_path / "out",
        state_dir=tmp_path / "state",
        poll_interval_s=1,
        max_concurrent_tasks=1,
        dry_run=False,
        pipeline=PipelineDefinition(
            execution_mode="bogus",  # type: ignore[arg-type]
            stages=[],
        ),
    )

    with pytest.raises(ValueError, match="Unsupported processor execution mode"):
        validate_pipeline(config)


def test_validate_pipeline_rejects_duplicate_stage_names(tmp_path: Path) -> None:
    duplicate_stage = dict(
        type="llm_map",
        input={"base_dir": "vault", "path": ".", "format": "json"},
        outputs=[
            {
                "name": "events",
                "collection": {"base_dir": "out", "path": "events", "format": "json"},
                "projection": "none",
                "result_key": "events",
                "kind": "event",
                "id_field": "event_id",
                "date_field": "date",
                "timestamp_field": "timestamp",
                "source_id_field": "source_raw_event_id",
            }
        ],
        enabled=True,
        state_key="dup",
        prompt="Clean event prompt",
        batch_size=1,
        flush_threshold=1,
        flush_when_upstream_empty=True,
        upstream=[],
        archive=None,
        transform_adapter="llm_map",
        transform_options={"input_mode": "raw", "input_key": "events"},
        concurrency=1,
    )
    config = ProcessorConfig(
        vault_dir=tmp_path / "vault",
        out_dir=tmp_path / "out",
        state_dir=tmp_path / "state",
        poll_interval_s=1,
        max_concurrent_tasks=1,
        dry_run=False,
        pipeline=PipelineDefinition(
            execution_mode="per_stage_worker",
            stages=[
                StageDefinition(name="dup", **duplicate_stage),
                StageDefinition(name="dup", **duplicate_stage),
            ],
        ),
    )

    with pytest.raises(ValueError, match="Duplicate processor stage name"):
        validate_pipeline(config)


def test_build_worker_specs_respects_execution_mode(tmp_path: Path) -> None:
    config = ProcessorConfig(
        vault_dir=tmp_path / "vault",
        out_dir=tmp_path / "out",
        state_dir=tmp_path / "state",
        poll_interval_s=1,
        max_concurrent_tasks=1,
        dry_run=False,
        pipeline=_processor_pipeline(),
    )

    specs = build_worker_specs(config)

    assert specs == [{"mode": "single_loop", "name": "processor-single-loop"}]
