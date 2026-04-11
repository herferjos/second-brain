from __future__ import annotations

from pathlib import Path


def resolve_note_path(vault_dir: Path, relative_path: str) -> Path:
    clean_path = Path(relative_path.strip())
    if clean_path.is_absolute():
        raise ValueError("note path must be relative to vault_dir")
    resolved = (vault_dir / clean_path).resolve()
    vault_root = vault_dir.resolve()
    if resolved != vault_root and vault_root not in resolved.parents:
        raise ValueError("note path escapes vault_dir")
    if resolved.suffix.lower() != ".md":
        raise ValueError("note path must end with .md")
    return resolved


def create_note(vault_dir: Path, relative_path: str, content: str) -> Path:
    note_path = resolve_note_path(vault_dir, relative_path)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    if note_path.exists():
        raise ValueError(f"note already exists: {relative_path}")
    note_path.write_text(content, encoding="utf-8")
    return note_path


def replace_note(vault_dir: Path, relative_path: str, content: str) -> Path:
    note_path = resolve_note_path(vault_dir, relative_path)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content, encoding="utf-8")
    return note_path


def append_note(vault_dir: Path, relative_path: str, content: str) -> Path:
    note_path = resolve_note_path(vault_dir, relative_path)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    if note_path.exists():
        previous = note_path.read_text(encoding="utf-8")
        note_path.write_text(previous + content, encoding="utf-8")
    else:
        note_path.write_text(content, encoding="utf-8")
    return note_path


def delete_note(vault_dir: Path, relative_path: str) -> Path:
    note_path = resolve_note_path(vault_dir, relative_path)
    if not note_path.exists():
        raise ValueError(f"note does not exist: {relative_path}")
    note_path.unlink()
    return note_path


def read_note(vault_dir: Path, relative_path: str) -> str:
    note_path = resolve_note_path(vault_dir, relative_path)
    if not note_path.exists():
        raise ValueError(f"note does not exist: {relative_path}")
    return note_path.read_text(encoding="utf-8")


def list_notes(vault_dir: Path) -> list[str]:
    if not vault_dir.exists():
        return []
    return sorted(str(path.relative_to(vault_dir)) for path in vault_dir.rglob("*.md") if path.is_file())
