"""Persist incoming files to tmp, write API responses to vault, then remove tmp."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from exocort import settings

    def _tmp_dir() -> Path:
        return settings.collector_tmp_dir()

    def _vault_dir() -> Path:
        return settings.collector_vault_dir()
except ImportError:
    def _tmp_dir() -> Path:
        return Path(os.environ.get("COLLECTOR_TMP_DIR", "tmp/collector")).resolve()

    def _vault_dir() -> Path:
        return Path(os.environ.get("COLLECTOR_VAULT_DIR", "vault")).resolve()


def _date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _timestamp_id() -> str:
    """Filesystem-safe ISO timestamp (no colons)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%f")[:-3]


def save_to_tmp(
    content: bytes,
    subdir: str,
    date: str,
    base_name: str,
    suffix: str,
) -> Path:
    """Save content under tmp/collector/{subdir}/{date}/{base_name}{suffix}. Returns path."""
    root = _tmp_dir() / subdir / date
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{base_name}{suffix}"
    path.write_bytes(content)
    return path


def write_vault_record(
    date: str,
    timestamp_iso: str,
    type_: str,
    id_: str,
    meta: dict[str, str],
    responses: list[dict[str, Any]],
) -> Path:
    """Write one JSON record to vault/{date}/{timestamp}_{type}_{id}.json."""
    root = _vault_dir() / date
    root.mkdir(parents=True, exist_ok=True)
    safe_ts = timestamp_iso.replace(":", "-")
    name = f"{safe_ts}_{type_}_{id_}.json"
    path = root / name
    record = {
        "timestamp": timestamp_iso,
        "type": type_,
        "id": id_,
        "meta": meta,
        "responses": responses,
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def remove_tmp(path: Path) -> None:
    path.unlink(missing_ok=True)
