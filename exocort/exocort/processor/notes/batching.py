from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from litellm import token_counter

from exocort.config import NotesSettings, ProcessorSettings

from .models import BatchCandidate, ProcessedArtifact
from .state import completed_artifact_ids
from .timeline import render_timeline, render_timeline_entry


def discover_unprocessed_artifacts(config: ProcessorSettings) -> list[ProcessedArtifact]:
    done_ids = completed_artifact_ids(config.notes.state_dir)
    artifacts: list[ProcessedArtifact] = []
    for json_path in sorted(config.output_dir.rglob("*.json")):
        if not json_path.is_file():
            continue
        artifact_id = str(json_path.relative_to(config.output_dir))
        if artifact_id.startswith("notes/"):
            continue
        if artifact_id in done_ids:
            continue
        try:
            artifact = load_artifact(config, json_path)
        except Exception:
            continue
        artifacts.append(artifact)
    artifacts.sort(key=lambda artifact: (artifact.captured_at, artifact.artifact_id))
    return artifacts


def build_batch_candidate(notes: NotesSettings, artifacts: list[ProcessedArtifact]) -> BatchCandidate | None:
    selected: list[ProcessedArtifact] = []
    selected_tokens = 0

    for artifact in artifacts:
        entry = render_timeline_entry(artifact)
        entry_tokens = token_counter(model=notes.model, text=entry)
        if selected and selected_tokens + entry_tokens > notes.max_input_tokens:
            break
        selected.append(artifact)
        selected_tokens += entry_tokens
        if selected_tokens >= notes.max_input_tokens:
            break

    if not selected:
        return None

    selected_tuple = tuple(selected)
    return BatchCandidate(
        artifacts=selected_tuple,
        input_text=render_timeline(selected_tuple),
        input_tokens=selected_tokens,
    )


def load_artifact(config: ProcessorSettings, json_path: Path) -> ProcessedArtifact:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("processed JSON must be an object")

    artifact_id = str(json_path.relative_to(config.output_dir))
    text = str(payload.get("text", "")).strip()
    if not text:
        raise ValueError("processed JSON text is empty")

    source_kind = _source_kind(payload, artifact_id)
    source_relpath = payload.get("source_relpath")
    if source_relpath is not None:
        source_relpath = str(source_relpath)
    source_file = payload.get("source_file")
    source_file_path = Path(str(source_file)) if source_file else None
    captured_at = _captured_at(payload, artifact_id)

    return ProcessedArtifact(
        artifact_id=artifact_id,
        source_kind=source_kind,
        json_path=json_path,
        source_file=source_file_path,
        source_relpath=source_relpath,
        captured_at=captured_at,
        text=text,
    )


def _source_kind(payload: dict[str, object], artifact_id: str) -> str:
    value = payload.get("source_kind")
    if value in {"ocr", "asr"}:
        return str(value)
    if artifact_id.endswith((".png.json", ".jpg.json", ".jpeg.json", ".webp.json", ".bmp.json", ".gif.json", ".tif.json", ".tiff.json")):
        return "ocr"
    if artifact_id.endswith((".wav.json", ".mp3.json", ".m4a.json", ".mp4.json", ".mpeg.json", ".mpga.json", ".webm.json", ".ogg.json")):
        return "asr"
    raise ValueError("cannot infer source_kind from legacy artifact")


def _captured_at(payload: dict[str, object], artifact_id: str) -> datetime:
    value = payload.get("captured_at")
    if isinstance(value, str) and value.strip():
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)

    base_name = Path(artifact_id).name
    parts = base_name.split(".")
    if len(parts) < 3:
        raise ValueError("cannot infer captured_at from legacy artifact")
    timestamp = parts[0]
    return datetime.strptime(timestamp, "%Y%m%dT%H%M%S%f").replace(tzinfo=timezone.utc)
