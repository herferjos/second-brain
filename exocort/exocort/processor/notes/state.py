from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def ensure_state_dirs(state_dir: Path) -> None:
    (state_dir / "batches").mkdir(parents=True, exist_ok=True)
    (state_dir / "errors").mkdir(parents=True, exist_ok=True)


def completed_artifact_ids(state_dir: Path) -> set[str]:
    batch_dir = state_dir / "batches"
    if not batch_dir.exists():
        return set()

    completed: set[str] = set()
    for batch_path in sorted(batch_dir.glob("*.json")):
        try:
            payload = json.loads(batch_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("status") != "completed":
            continue
        artifact_ids = payload.get("artifact_ids")
        if not isinstance(artifact_ids, list):
            continue
        completed.update(str(value) for value in artifact_ids)
    return completed


def write_batch_manifest(
    state_dir: Path,
    *,
    batch_id: str,
    status: str,
    artifact_ids: list[str],
    input_tokens: int,
    note_paths: list[str],
    assistant_message: str,
    tool_results: list[dict[str, str | None]],
    error: str | None,
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "batch_id": batch_id,
        "status": status,
        "created_at": now,
        "finished_at": now,
        "artifact_ids": artifact_ids,
        "input_tokens": input_tokens,
        "note_paths": note_paths,
        "assistant_message": assistant_message,
        "tool_results": tool_results,
        "error": error,
    }
    manifest_path = state_dir / "batches" / f"{batch_id}.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def write_batch_error(state_dir: Path, batch_id: str, error: str) -> Path:
    error_path = state_dir / "errors" / f"{batch_id}.txt"
    error_path.write_text(error, encoding="utf-8")
    return error_path
