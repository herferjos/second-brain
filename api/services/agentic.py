import os
from datetime import date
from typing import Any

from api.config import settings
from api.services.llm import run_json_completion
from api.services.notes import extract_wikilinks, list_files, read_file, search_text, write_file


_DEFAULT_SKILL_PROMPT = """You are a controller for a personal knowledge base stored as Markdown.

Principles:
- Prefer atomic notes.
- Use YAML frontmatter for metadata (date, tags, status).
- Use Obsidian wikilinks [[Like This]] to connect existing notes.
- Do not invent facts not present in the input/context.
"""


_DEFAULT_ARCHIVIST_SYSTEM = """You are The Archivist: you convert raw input into structured Markdown notes in a personal vault.

Workflow requirements:
1) Discovery: before writing, identify key entities/topics and check if related notes already exist.
2) Note creation/update:
   - Produce one atomic note.
   - Use YAML frontmatter.
   - Use [[Wikilinks]] for entities that exist or should exist.
   - If the input is an update to an existing note, append to it (do not rewrite the whole file).
3) Cross-referencing:
   - Add a 'Context' section explaining how this note connects to other notes.

Output rules:
- Return ONLY valid JSON (no extra text).
"""


_DEFAULT_RESEARCHER_SYSTEM = """You are The Researcher: you answer questions using ONLY the user's Markdown vault.

Protocol:
1) Analyze: turn the question into keywords.
2) Search: select relevant notes.
3) Read & navigate: if a note mentions a [[Link]] that seems crucial, follow it.
4) Synthesize: answer and cite sources (file paths).

If you cannot find the answer in the files, say:
"Your digital twin does not have this information yet."

Output rules:
- Return ONLY valid JSON (no extra text).
"""


def _prompt_path(name: str) -> str:
    return os.path.join(settings.VAULT_PROMPTS_PATH, name)


def _read_or_create_prompt(filename: str, default_content: str) -> str:
    path = _prompt_path(filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(default_content.strip() + "\n")
    return default_content


def ensure_default_prompts():
    _read_or_create_prompt("_sb_skill.md", _DEFAULT_SKILL_PROMPT)
    _read_or_create_prompt("_sb_archivist_system.md", _DEFAULT_ARCHIVIST_SYSTEM)
    _read_or_create_prompt("_sb_researcher_system.md", _DEFAULT_RESEARCHER_SYSTEM)


def _note_titles_from_paths(paths: list[str]) -> list[str]:
    titles: list[str] = []
    for p in paths:
        base = os.path.basename(p)
        if base.lower().endswith(".md"):
            base = base[: -len(".md")]
        if base and base not in titles:
            titles.append(base)
    return titles


def _unique(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def archivist_ingest(raw_data: str, *, job_id: str = "unknown") -> dict[str, Any]:
    ensure_default_prompts()

    skill = _read_or_create_prompt("_sb_skill.md", _DEFAULT_SKILL_PROMPT)
    system = _read_or_create_prompt("_sb_archivist_system.md", _DEFAULT_ARCHIVIST_SYSTEM)

    discovery_user = (
        "RAW DATA:\n"
        f"{raw_data}\n\n"
        "Return JSON with keys:\n"
        "- keywords: array of strings (3-8)\n"
        "- title: short string\n"
        "- operation: 'create' or 'update'\n"
        "- target_hint: optional string (existing note title or path if update)\n"
    )
    discovery = run_json_completion(
        messages=[
            {"role": "system", "content": skill + "\n\n" + system},
            {"role": "user", "content": discovery_user},
        ],
        temperature=0.2,
        max_tokens=512,
    ) or {}

    keywords = discovery.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    keywords = [str(k).strip() for k in keywords if str(k).strip()][:8]

    related_paths: list[str] = []
    for kw in keywords[:5]:
        for hit in search_text(kw, regex=False, limit_hits=50):
            related_paths.append(hit.path)
    related_paths = _unique(related_paths)[:30]
    related_titles = _note_titles_from_paths(related_paths)

    operation = str(discovery.get("operation") or "create").strip().lower()
    existing_note: dict[str, Any] | None = None
    if operation == "update" and related_paths:
        try:
            existing_note = read_file(related_paths[0], max_chars=6000)
        except Exception:
            existing_note = None

    today = date.today().isoformat()
    write_user = (
        "You must produce the final note.\n\n"
        f"RAW DATA:\n{raw_data}\n\n"
        f"TODAY: {today}\n\n"
        "EXISTING NOTE TITLES IN THIS VAULT (use [[Wikilinks]] matching these when relevant):\n"
        + "\n".join(f"- {t}" for t in related_titles)
        + "\n\n"
        "EXISTING NOTE PATHS (for reference):\n"
        + "\n".join(f"- {p}" for p in related_paths)
        + "\n\n"
    )
    if existing_note:
        write_user += (
            "POSSIBLE TARGET NOTE CONTENT (for updates):\n"
            f"PATH: {existing_note['path']}\n"
            f"{existing_note['content']}\n\n"
        )

    write_user += (
        "Return JSON with keys:\n"
        "- path: relative Markdown path (prefer 'YYYY-MM-DD - Title.md' in vault root)\n"
        "- content: Markdown string\n"
        "- write_mode: 'overwrite' or 'append' (append if this is an update)\n"
    )

    write_plan = run_json_completion(
        messages=[
            {"role": "system", "content": skill + "\n\n" + system},
            {"role": "user", "content": write_user},
        ],
        temperature=0.2,
        max_tokens=settings.LLM_MAX_TOKENS,
    ) or {}

    target_path = str(write_plan.get("path") or "").strip()
    content = str(write_plan.get("content") or "").strip()
    write_mode = str(write_plan.get("write_mode") or "overwrite").strip().lower()
    if write_mode not in {"overwrite", "append"}:
        write_mode = "overwrite"

    if not target_path:
        target_path = f"{today} - Untitled.md"

    write_result = write_file(target_path, content, mode=write_mode)
    return {
        "job_id": job_id,
        "path": write_result["path"],
        "write_mode": write_result["mode"],
        "keywords": keywords,
        "related_paths": related_paths,
    }


def _build_title_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for p in list_files(limit=5000):
        title = os.path.basename(p)
        if title.lower().endswith(".md"):
            title = title[: -len(".md")]
        if title and title not in index:
            index[title] = p
    return index


def researcher_answer(question: str, *, job_id: str = "unknown") -> dict[str, Any]:
    ensure_default_prompts()

    skill = _read_or_create_prompt("_sb_skill.md", _DEFAULT_SKILL_PROMPT)
    system = _read_or_create_prompt("_sb_researcher_system.md", _DEFAULT_RESEARCHER_SYSTEM)

    plan_user = (
        f"QUESTION:\n{question}\n\n"
        "Return JSON with keys:\n"
        "- keywords: array of strings (3-8)\n"
        "- follow_wikilinks: boolean\n"
    )
    plan = run_json_completion(
        messages=[
            {"role": "system", "content": skill + "\n\n" + system},
            {"role": "user", "content": plan_user},
        ],
        temperature=0.2,
        max_tokens=384,
    ) or {}

    keywords = plan.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    keywords = [str(k).strip() for k in keywords if str(k).strip()][:8]
    follow_wikilinks = bool(plan.get("follow_wikilinks", True))

    candidate_paths: list[str] = []
    for kw in keywords[:6]:
        for hit in search_text(kw, regex=False, limit_hits=80):
            candidate_paths.append(hit.path)
    candidate_paths = _unique(candidate_paths)[:15]

    read_notes: list[dict[str, Any]] = []
    for p in candidate_paths:
        try:
            read_notes.append(read_file(p, max_chars=8000))
        except Exception:
            continue

    sources: list[str] = [n["path"] for n in read_notes]

    if follow_wikilinks and read_notes:
        title_index = _build_title_index()
        link_titles: list[str] = []
        for n in read_notes[:8]:
            link_titles.extend(extract_wikilinks(n.get("content", ""))[:20])
        link_titles = _unique([t for t in link_titles if t])[:10]

        for title in link_titles:
            path = title_index.get(title)
            if not path or path in sources:
                continue
            try:
                read_notes.append(read_file(path, max_chars=8000))
                sources.append(path)
            except Exception:
                continue

    context_blob = ""
    for note in read_notes[:12]:
        context_blob += f"\n\n---\nSOURCE: {note['path']}\n{note['content']}\n"

    answer_user = (
        f"QUESTION:\n{question}\n\n"
        "SOURCES:\n"
        + "\n".join(f"- {p}" for p in sources)
        + "\n\n"
        "CONTENT:\n"
        + context_blob
        + "\n\nReturn JSON with keys:\n"
        "- answer: string\n"
        "- sources: array of file paths you used\n"
    )
    result = run_json_completion(
        messages=[
            {"role": "system", "content": skill + "\n\n" + system},
            {"role": "user", "content": answer_user},
        ],
        temperature=0.2,
        max_tokens=settings.LLM_MAX_TOKENS,
    ) or {}

    answer = str(result.get("answer") or "").strip()
    used_sources = result.get("sources") or sources
    if not isinstance(used_sources, list):
        used_sources = sources
    used_sources = [str(s).strip() for s in used_sources if str(s).strip()]

    return {"job_id": job_id, "answer": answer, "sources": _unique(used_sources)}

