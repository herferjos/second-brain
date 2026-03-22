"""Configurable orchestration layer for the processor pipeline."""

from __future__ import annotations

import logging
import multiprocessing
import time
from pathlib import Path

from exocort import settings

from .adapters import InputItem, execute_stage_adapter
from .artifacts import markdown_filename, render_markdown
from .config import AppConfig, load_app_config
from .llm import ProcessorLLMClient, SemaphoreLLMClient, SupportsLLMClient
from .models import ArtifactEnvelope, CollectionDefinition, OutputDefinition, ProcessorConfig, StageDefinition
from .storage import (
    list_collection_paths,
    load_artifact,
    load_state,
    resolve_collection_dir,
    rewrite_jsonl_day,
    save_state,
)
from .utils import atomic_write_json, atomic_write_text, canonical_path, ensure_parent, load_json, pending_paths


def validate_pipeline(config: ProcessorConfig) -> None:
    execution_mode = config.execution_mode
    if execution_mode not in {"per_stage_worker", "single_loop"}:
        raise ValueError(f"Unsupported processor execution mode: {execution_mode!r}")
    if not config.stages:
        raise ValueError("Processor pipeline must define at least one enabled stage")

    seen_names: set[str] = set()
    for stage in config.stages:
        if stage.name in seen_names:
            raise ValueError(f"Duplicate processor stage name: {stage.name}")
        seen_names.add(stage.name)
        if not stage.outputs:
            raise ValueError(f"Stage {stage.name} must define at least one output")
        if stage.transform_adapter != stage.type and stage.transform_adapter != "noop":
            raise ValueError(
                f"Stage {stage.name} transform_adapter must match type or be 'noop'; got {stage.transform_adapter!r}"
            )
        if stage.type.startswith("llm_") and not stage.prompt:
            raise ValueError(f"Stage {stage.name} requires prompt")
        for output in stage.outputs:
            if output.projection == "jsonl_day" and output.projection_target is None:
                raise ValueError(f"Stage {stage.name} output {output.name} requires projection_target for jsonl_day")
            if output.projection != "jsonl_day" and output.projection_target is not None:
                raise ValueError(f"Stage {stage.name} output {output.name} projection_target is only valid for jsonl_day")


def run_once(
    config: ProcessorConfig,
    client: SupportsLLMClient | None = None,
    app_config: AppConfig | None = None,
) -> int:
    config.out_dir.mkdir(parents=True, exist_ok=True)
    config.state_dir.mkdir(parents=True, exist_ok=True)
    validate_pipeline(config)

    effective_client = client
    if effective_client is None:
        effective_app_config = app_config or load_app_config()
        effective_client = ProcessorLLMClient(effective_app_config.llm)

    processed = 0
    for stage in config.stages:
        processed += run_stage_once(config, stage, effective_client)
    return processed


def _collection_paths(config: ProcessorConfig, collection: CollectionDefinition) -> list[Path]:
    return list_collection_paths(config, collection)


def _upstream_pending(config: ProcessorConfig, stage: StageDefinition) -> bool:
    return any(bool(_collection_paths(config, collection)) for collection in stage.upstream)


def _should_flush(pending_count: int, stage: StageDefinition, upstream_pending: bool) -> bool:
    if pending_count <= 0:
        return False
    if pending_count >= stage.flush_threshold:
        return True
    return stage.flush_when_upstream_empty and not upstream_pending


def _load_input_item(config: ProcessorConfig, stage: StageDefinition, path: Path) -> InputItem:
    raw = load_json(path)
    envelope = None
    if stage.input.base_dir != "vault":
        envelope = load_artifact(path)
    return InputItem(path=path, raw=raw if isinstance(raw, dict) else {}, envelope=envelope)


def _artifact_json_path(config: ProcessorConfig, output: OutputDefinition, envelope: ArtifactEnvelope) -> Path:
    root = resolve_collection_dir(config, output.collection)
    return root / envelope.date / f"{envelope.item_id}.json"


def _write_output_projection(
    config: ProcessorConfig,
    output: OutputDefinition,
    envelopes: list[ArtifactEnvelope],
) -> tuple[list[Path], set[str]]:
    written_paths: list[Path] = []
    touched_dates: set[str] = set()
    if output.projection == "markdown_note":
        for envelope in envelopes:
            date, filename = markdown_filename(envelope)
            path = resolve_collection_dir(config, output.collection) / date / filename
            if not config.dry_run:
                atomic_write_text(path, render_markdown(envelope))
            written_paths.append(path)
            touched_dates.add(envelope.date)
        return written_paths, touched_dates

    for envelope in envelopes:
        path = _artifact_json_path(config, output, envelope)
        if not config.dry_run:
            atomic_write_json(path, envelope.to_dict())
        written_paths.append(path)
        touched_dates.add(envelope.date)

    if output.projection == "jsonl_day" and not config.dry_run:
        assert output.projection_target is not None
        for date in touched_dates:
            rewrite_jsonl_day(config, output.collection, output.projection_target, date)
    return written_paths, touched_dates


def _archive_inputs(config: ProcessorConfig, stage: StageDefinition, batch_paths: list[Path]) -> None:
    if not stage.archive or config.dry_run:
        return
    archive_root = resolve_collection_dir(config, stage.archive)
    for path in batch_paths:
        date = path.parent.name
        archive_path = archive_root / date / path.name
        ensure_parent(archive_path)
        path.replace(archive_path)


def run_stage_once(config: ProcessorConfig, stage: StageDefinition, client: SupportsLLMClient) -> int:
    state = load_state(config, stage.state_key or stage.name)
    all_input_paths = _collection_paths(config, stage.input)
    batch_candidates = pending_paths(all_input_paths, state.cursor_path)
    upstream_pending = _upstream_pending(config, stage)
    if not _should_flush(len(batch_candidates), stage, upstream_pending):
        return 0

    batch_paths = batch_candidates[: stage.batch_size] if len(batch_candidates) >= stage.batch_size else batch_candidates
    items = [_load_input_item(config, stage, path) for path in batch_paths]
    outputs_by_name = execute_stage_adapter(stage, config, items, client)

    processed_items: set[tuple[str, str]] = set()
    last_output_id: str | None = None
    last_output_path: str | None = None
    for output in stage.outputs:
        envelopes = outputs_by_name.get(output.name, [])
        written_paths, _ = _write_output_projection(config, output, envelopes)
        processed_items.update((envelope.kind, envelope.item_id) for envelope in envelopes)
        if written_paths and envelopes:
            last_output_path = canonical_path(written_paths[-1])
            last_output_id = envelopes[-1].item_id

    _archive_inputs(config, stage, batch_paths)

    if batch_paths:
        state.cursor_path = canonical_path(batch_paths[-1])
        state.cursor_id = batch_paths[-1].stem
    if last_output_path:
        state.last_output_path = last_output_path
    if last_output_id:
        state.last_output_id = last_output_id
    save_state(config, stage.state_key or stage.name, state)
    return len(processed_items)


def _worker_loop(name: str, config: ProcessorConfig, stage: StageDefinition, client: SupportsLLMClient) -> None:
    while True:
        try:
            processed = run_stage_once(config, stage, client)
            if processed:
                logging.info("%s worker processed %s items", name, processed)
            else:
                logging.info("%s worker idle", name)
        except Exception:
            logging.exception("%s worker failed", name)
        time.sleep(config.poll_interval_s)


def _configure_worker_logging() -> None:
    logging.getLogger().setLevel(settings.log_level())


def _build_worker_client(app_config: AppConfig, semaphore: multiprocessing.Semaphore) -> SupportsLLMClient:
    return SemaphoreLLMClient(ProcessorLLMClient(app_config.llm), semaphore)


def _stage_worker(config: ProcessorConfig, app_config: AppConfig, semaphore: multiprocessing.Semaphore, stage_name: str) -> None:
    _configure_worker_logging()
    stage = next(stage for stage in config.stages if stage.name == stage_name)
    client = _build_worker_client(app_config, semaphore)
    _worker_loop(stage.name, config, stage, client)


def _single_loop_worker(config: ProcessorConfig, app_config: AppConfig, semaphore: multiprocessing.Semaphore) -> None:
    _configure_worker_logging()
    client = _build_worker_client(app_config, semaphore)
    while True:
        try:
            processed = 0
            for stage in config.stages:
                processed += run_stage_once(config, stage, client)
            if processed:
                logging.info("processor single loop processed %s items", processed)
            else:
                logging.info("processor single loop idle")
        except Exception:
            logging.exception("processor single loop failed")
        time.sleep(config.poll_interval_s)


def build_worker_specs(config: ProcessorConfig) -> list[dict[str, str]]:
    validate_pipeline(config)
    if config.execution_mode == "single_loop":
        return [{"mode": "single_loop", "name": "processor-single-loop"}]
    return [{"mode": "per_stage_worker", "name": stage.name} for stage in config.stages]


def run_worker_spec(
    config: ProcessorConfig,
    app_config: AppConfig,
    semaphore: multiprocessing.Semaphore,
    spec: dict[str, str],
) -> None:
    if spec["mode"] == "single_loop":
        _single_loop_worker(config, app_config, semaphore)
        return
    _stage_worker(config, app_config, semaphore, spec["name"])
