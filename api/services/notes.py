import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from api.config import settings

_SYSTEM_DIRS = {"_logs"}
_SYSTEM_FILE_PREFIXES = ("_sb_",)


@dataclass(frozen=True)
class SearchHit:
    path: str
    line_number: int
    line: str


def _normalize_relative_path(raw_path: str) -> str:
    raw_path = (raw_path or "").replace("\\", "/").strip()
    if not raw_path:
        return ""
    raw_path = raw_path.lstrip("/")

    parts = [p.strip() for p in raw_path.split("/") if p.strip() and p.strip() != "."]
    if not parts or any(p == ".." for p in parts):
        raise ValueError("Unsafe path")

    return "/".join(parts)


def _safe_join_vault(relative_path: str) -> str:
    vault_root = os.path.abspath(settings.VAULT_PATH)
    target = os.path.abspath(os.path.join(vault_root, relative_path))
    if os.path.commonpath([vault_root, target]) != vault_root:
        raise ValueError("Path escapes vault")
    return target


def list_files(
    directory: str = "",
    *,
    extensions: Iterable[str] = (".md",),
    include_system: bool = False,
    limit: int = 5000,
) -> list[str]:
    rel_dir = _normalize_relative_path(directory) if directory else ""
    base = _safe_join_vault(rel_dir) if rel_dir else os.path.abspath(settings.VAULT_PATH)

    results: list[str] = []
    vault_root = os.path.abspath(settings.VAULT_PATH)

    for root, dirs, files in os.walk(base):
        if not include_system:
            dirs[:] = [d for d in dirs if d not in _SYSTEM_DIRS]

        for name in files:
            if not include_system and any(name.startswith(prefix) for prefix in _SYSTEM_FILE_PREFIXES):
                continue
            if extensions and not any(name.lower().endswith(ext) for ext in extensions):
                continue
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, start=vault_root).replace("\\", "/")
            results.append(rel_path)
            if len(results) >= limit:
                return sorted(results)

    return sorted(results)


def read_file(path: str, *, max_chars: int | None = None) -> dict:
    rel_path = _normalize_relative_path(path)
    full_path = _safe_join_vault(rel_path)

    if not os.path.exists(full_path):
        raise FileNotFoundError(rel_path)
    if not os.path.isfile(full_path):
        raise IsADirectoryError(rel_path)

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()

    if max_chars is not None and len(content) > max_chars:
        content = content[:max_chars] + "\n\n<!-- truncated -->\n"

    stat = os.stat(full_path)
    return {
        "path": rel_path,
        "content": content,
        "bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


def write_file(path: str, content: str, *, mode: str = "overwrite") -> dict:
    rel_path = _normalize_relative_path(path)
    if not rel_path.lower().endswith(".md"):
        rel_path += ".md"

    full_path = _safe_join_vault(rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    if mode not in {"overwrite", "append"}:
        raise ValueError("mode must be 'overwrite' or 'append'")

    file_mode = "a" if mode == "append" else "w"
    with open(full_path, file_mode, encoding="utf-8") as f:
        if file_mode == "a" and content:
            f.write("\n\n" + content)
        else:
            f.write(content)

    return {"path": rel_path, "mode": mode}


def search_text(
    query: str,
    *,
    directory: str = "",
    regex: bool = True,
    case_insensitive: bool = True,
    limit_hits: int = 200,
    max_file_bytes: int = 2_000_000,
) -> list[SearchHit]:
    if not query or not query.strip():
        return []

    flags = re.IGNORECASE if case_insensitive else 0
    pattern = re.compile(query if regex else re.escape(query), flags=flags)

    hits: list[SearchHit] = []
    for rel_path in list_files(directory, include_system=False, limit=5000):
        full_path = _safe_join_vault(rel_path)
        try:
            if os.path.getsize(full_path) > max_file_bytes:
                continue
        except OSError:
            continue

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                for idx, line in enumerate(f, start=1):
                    if pattern.search(line):
                        hits.append(
                            SearchHit(
                                path=rel_path,
                                line_number=idx,
                                line=line.rstrip("\n"),
                            )
                        )
                        if len(hits) >= limit_hits:
                            return hits
        except (OSError, UnicodeDecodeError):
            continue

    return hits


_WIKILINK_RE = re.compile(r"\[\[([^\]\|#]+)(?:[^\]]*)\]\]")


def extract_wikilinks(markdown: str) -> list[str]:
    if not markdown:
        return []
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(markdown) if m.group(1).strip()]

