"""Persistence helpers for processor artifacts and state."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ArtifactEnvelope, CollectionDefinition, ProcessorConfig, ProcessorState
from .utils import atomic_write_json, atomic_write_text, iter_json_files_recursive, load_json, utc_iso


def resolve_collection_dir(config: ProcessorConfig, collection: CollectionDefinition) -> Path:
    base = config.out_dir
    if collection.base_dir == "vault":
        base = config.vault_dir
    elif collection.base_dir == "state":
        base = config.state_dir
    path = Path(collection.path)
    if path == Path("."):
        return base
    return base / path


def state_file(config: ProcessorConfig, name: str) -> Path:
    return config.state_dir / f"state_{name}.json"


def load_state(config: ProcessorConfig, name: str) -> ProcessorState:
    path = state_file(config, name)
    if not path.exists():
        return ProcessorState()
    data = load_json(path)
    return ProcessorState.from_dict(data if isinstance(data, dict) else {})


def save_state(config: ProcessorConfig, name: str, state: ProcessorState) -> None:
    state.last_run_at = utc_iso()
    atomic_write_json(state_file(config, name), state.to_dict())


def projection_jsonl_path(config: ProcessorConfig, collection: CollectionDefinition, date: str) -> Path:
    return resolve_collection_dir(config, collection) / f"{date}.jsonl"


def rewrite_jsonl_day(config: ProcessorConfig, source: CollectionDefinition, target: CollectionDefinition, date: str) -> None:
    source_dir = resolve_collection_dir(config, source) / date
    entries = [load_json(path) for path in sorted(source_dir.glob("*.json"))] if source_dir.exists() else []
    entries.sort(
        key=lambda item: (
            str(item.get("timestamp") or ""),
            str(item.get("payload", {}).get("timestamp_end") or ""),
            str(item.get("item_id") or ""),
        )
    )
    text = ""
    if entries:
        lines = [json.dumps(item.get("payload", item), ensure_ascii=False) for item in entries]
        text = "\n".join(lines) + "\n"
    atomic_write_text(projection_jsonl_path(config, target, date), text)


def list_collection_paths(config: ProcessorConfig, collection: CollectionDefinition) -> list[Path]:
    return iter_json_files_recursive(resolve_collection_dir(config, collection))


def load_artifact(path: Path) -> ArtifactEnvelope:
    data = load_json(path)
    return ArtifactEnvelope.from_dict(data if isinstance(data, dict) else {})
