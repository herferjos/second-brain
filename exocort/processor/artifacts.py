"""Artifact rendering helpers."""

from __future__ import annotations

import json
from typing import Any

from .models import ArtifactEnvelope
from .utils import utc_iso


def markdown_filename(envelope: ArtifactEnvelope) -> tuple[str, str]:
    return envelope.date, f"{envelope.item_id}.md"


def render_markdown(envelope: ArtifactEnvelope | dict[str, Any]) -> str:
    value = envelope if isinstance(envelope, ArtifactEnvelope) else ArtifactEnvelope.from_dict(envelope)
    frontmatter = {
        "kind": value.kind,
        "stage": value.stage,
        "item_id": value.item_id,
        "timestamp": value.timestamp,
        "date": value.date,
        "source_ids": value.source_ids,
        "source_paths": value.source_paths,
        "trace": value.trace,
        "updated_at": utc_iso(),
    }
    lines = ["---"]
    for key, item in frontmatter.items():
        lines.append(f"{key}: {json.dumps(item, ensure_ascii=False)}")
    lines.extend(
        [
            "---",
            "",
            f"# {value.item_id}",
            "",
            "```json",
            json.dumps(value.payload, ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)
