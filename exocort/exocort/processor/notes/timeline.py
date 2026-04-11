from __future__ import annotations

from .models import ProcessedArtifact


def render_timeline_entry(artifact: ProcessedArtifact) -> str:
    label = "Pantalla mostraba" if artifact.source_kind == "ocr" else "Audio decía"
    source_ref = artifact.source_relpath or artifact.artifact_id
    text = artifact.text.strip()
    return (
        f"[{artifact.captured_at.isoformat()}] [{artifact.source_kind}] {source_ref}\n"
        f"{label}: {text}"
    )


def render_timeline(artifacts: tuple[ProcessedArtifact, ...]) -> str:
    return "\n\n".join(render_timeline_entry(artifact) for artifact in artifacts).strip()
