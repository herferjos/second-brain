"""LLM-first vault processor with persistent per-level state."""

from __future__ import annotations

import copy
import json
import logging
import multiprocessing
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import AppConfig, LLMConfig

import requests


# Re-introduce ProcessorConfig dataclass
@dataclass
class ProcessorConfig:
    vault_dir: Path
    out_dir: Path
    state_dir: Path
    poll_interval_seconds: int
    l1_group_size: int
    l2_trigger_threshold: int
    l3_trigger_threshold: int
    l4_enabled: bool
    l4_interval_hours: int
    dry_run: bool = False # Add a dry_run flag, you can control it from settings



# --- Helper Functions ---

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_date() -> str:
    return _utc_now().strftime("%Y-%m-%d")


def _utc_iso() -> str:
    return _utc_now().isoformat()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned or "item"


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "-", value.lower()).strip("-")
    return cleaned or "note"


def _date_from_timestamp(timestamp: str | None) -> str:
    if timestamp and len(timestamp) >= 10:
        return timestamp[:10]
    return _utc_date()


def _default_user_model() -> dict[str, Any]:
    return {
        "skills": [],
        "domains": [],
        "projects": [],
        "tools": [],
        "interests": [],
        "preferences": [],
        "people": [],
        "orgs": [],
        "open_questions": [],
    }


def _normalize_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _iter_date_dirs(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    dirs = [p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)]
    return sorted(dirs, key=lambda p: p.name)


def _iter_json_files_recursive(root: Path) -> list[Path]:
    """Iterates through JSON files in date-based subdirectories."""
    if not root.exists():
        return []
    paths: list[Path] = []
    for date_dir in _iter_date_dirs(root):
        paths.extend(sorted(date_dir.glob("*.json"), key=lambda p: p.name))
    return paths


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json_or_default(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return copy.deepcopy(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(default)
    if isinstance(data, dict):
        return data
    return copy.deepcopy(default)


def _atomic_write_text(path: Path, text: str) -> None:
    _ensure_parent(path)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_meta(meta: Any) -> dict[str, Any]:
    if not isinstance(meta, dict):
        return {}
    out: dict[str, Any] = copy.deepcopy(meta)
    for key in ("app", "capture", "permissions", "window"):
        value = out.get(key)
        if isinstance(value, str) and value.strip().startswith("{"):
            try:
                out[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return out


def _extract_text_from_data(data: Any) -> str | None:
    if isinstance(data, dict):
        for key in ("markdown", "text", "output_text", "content"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
                    if isinstance(content, list):
                        parts = []
                        for item in content:
                            if isinstance(item, dict) and isinstance(item.get("text"), str):
                                parts.append(item["text"])
                        if parts:
                            return "\n".join(parts)
                delta = first.get("delta")
                if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                    return delta["content"]
        return None
    if isinstance(data, list):
        parts = []
        for item in data:
            extracted = _extract_text_from_data(item)
            if extracted:
                parts.append(extracted)
        if parts:
            return "\n".join(parts)
    return None


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    return stripped.strip()


def _parse_json_payload(text: str | dict[str, Any] | list[Any]) -> Any:
    if isinstance(text, (dict, list)):
        return text
    candidate = _strip_code_fences(text.strip())
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        for anchor in ("{", "["):
            idx = candidate.find(anchor)
            if idx < 0:
                continue
            try:
                value, _ = json.JSONDecoder().raw_decode(candidate[idx:])
                return value
            except json.JSONDecodeError:
                continue
    raise ValueError("LLM response did not contain valid JSON")


def _extract_record_text(record: dict[str, Any]) -> str:
    parts: list[str] = []
    for response in record.get("responses") or []:
        if not isinstance(response, dict):
            continue
        raw = response.get("text") or response.get("raw") or ""
        if not isinstance(raw, str):
            continue
        piece = _extract_text_fragment(raw)
        if piece:
            parts.append(piece)
    return "\n\n".join(parts).strip()


def _extract_text_fragment(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return text
        extracted = _extract_text_from_data(data)
        if extracted:
            return extracted.strip()
    return text


def _response_text(response: requests.Response) -> str:
    try:
        parsed = response.json()
    except ValueError:
        return response.text.strip()
    extracted = _extract_text_from_data(parsed)
    if extracted:
        return extracted.strip()
    if isinstance(parsed, dict):
        return json.dumps(parsed, ensure_ascii=False)
    if isinstance(parsed, list):
        return json.dumps(parsed, ensure_ascii=False)
    return response.text.strip()


def _build_prompt_payload(level: str, prompt: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return [
        {"role": "system", "content": prompt.strip()},
        {
            "role": "user",
            "content": f"Level: {level}\n\nInput:\n{body}",
        },
    ]


def _normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    out = {str(k): str(v) for k, v in headers.items()}
    lowered = {k.lower() for k in out}
    if "content-type" not in lowered:
        out["Content-Type"] = "application/json"
    return out


# Removed ProcessorConfig dataclass as it's now imported from .config

@dataclass
class ProcessorState:
    last_raw_event_id: str | None = None
    last_raw_path: str | None = None
    last_l1_event_id: str | None = None
    last_l1_path: str | None = None
    last_l2_event_id: str | None = None
    last_l2_path: str | None = None
    last_timeline_event_key: str | None = None
    last_day_processed: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_raw_event_id": self.last_raw_event_id,
            "last_raw_path": self.last_raw_path,
            "last_l1_event_id": self.last_l1_event_id,
            "last_l1_path": self.last_l1_path,
            "last_l2_event_id": self.last_l2_event_id,
            "last_l2_path": self.last_l2_path,
            "last_timeline_event_key": self.last_timeline_event_key,
            "last_day_processed": self.last_day_processed,
            "updated_at": self.updated_at or _utc_iso(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProcessorState":
        return cls(
            last_raw_event_id=data.get("last_raw_event_id") or data.get("last_event_id") or None,
            last_raw_path=data.get("last_raw_path") or data.get("last_path") or None,
            last_l1_event_id=data.get("last_l1_event_id") or None,
            last_l1_path=data.get("last_l1_path") or None,
            last_l2_event_id=data.get("last_l2_event_id") or None,
            last_l2_path=data.get("last_l2_path") or None,
            last_timeline_event_key=data.get("last_timeline_event_key") or None,
            last_day_processed=data.get("last_day_processed") or None,
            updated_at=data.get("updated_at") or None,
        )


class ProcessorLLMClient:
    def __init__(self, llm_config: LLMConfig, prompts: dict[str, str], timeout_s: float = 60.0) -> None:
        self._config = llm_config
        self._prompts = prompts
        self._timeout_s = timeout_s

    def complete_json(self, prompt_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        response_text = self._complete(prompt_key, payload)
        parsed = _parse_json_payload(response_text)
        if isinstance(parsed, dict):
            return parsed
        return {"items": parsed}

    def complete_text(self, prompt_key: str, payload: dict[str, Any]) -> str:
        return self._complete(prompt_key, payload)

    def _complete(self, prompt_key: str, payload: dict[str, Any]) -> str:
        url = self._config.url
        if not url:
            raise RuntimeError("Processor LLM URL is not configured")

        prompt = self._prompts.get(prompt_key) or prompt_key
        body = copy.deepcopy(self._config.body)
        body["messages"] = _build_prompt_payload(prompt_key, prompt, payload)
        headers = _normalize_headers(self._config.headers)

        response = requests.post(
            url,
            json=body,
            headers=headers,
            timeout=self._timeout_s,
        )
        if not response.ok:
            raise RuntimeError(f"LLM request failed with status {response.status_code}: {response.text.strip()}")
        text = _response_text(response)
        if not text:
            raise RuntimeError("LLM response was empty")
        return text


def _state_file(config: ProcessorConfig, name: str) -> Path:
    assert config.state_dir is not None
    return config.state_dir / f"state_{name}.json"


def _load_state(config: ProcessorConfig, name: str) -> ProcessorState:
    path = _state_file(config, name)
    if not path.exists():
        return ProcessorState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ProcessorState()
    if not isinstance(data, dict):
        return ProcessorState()
    return ProcessorState.from_dict(data)


def _save_state(config: ProcessorConfig, name: str, state: ProcessorState) -> None:
    path = _state_file(config, name)
    _ensure_parent(path)
    state.updated_at = _utc_iso()
    _atomic_write_json(path, state.to_dict())


def _raw_event_id(record: dict[str, Any], path: Path) -> str:
    return _safe_id(str(record.get("id") or path.stem))


def _build_l1_payload(record: dict[str, Any], path: Path) -> dict[str, Any]:
    timestamp = str(record.get("timestamp") or "")
    meta = _parse_meta(record.get("meta") or {})
    text = _extract_record_text(record)
    return {
        "raw_event_id": _raw_event_id(record, path),
        "timestamp": timestamp,
        "type": str(record.get("type") or "unknown"),
        "id": str(record.get("id") or ""),
        "meta": meta,
        "responses": record.get("responses") or [],
        "raw_text": text,
        "source_path": str(path),
    }


def _build_l1_batch_payload(records: list[dict[str, Any]], paths: list[Path]) -> dict[str, Any]:
    return {
        "events": [
            _build_l1_payload(record, path)
            for record, path in zip(records, paths, strict=False)
        ]
    }


def _normalize_l1_output(
    result: dict[str, Any],
    record: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    payload = _build_l1_payload(record, path)
    timestamp = str(result.get("timestamp") or payload["timestamp"] or "")
    event_id = _safe_id(str(result.get("l1_event_id") or payload["raw_event_id"]))
    title = str(result.get("title") or "")
    clean_text = str(result.get("clean_text") or payload["raw_text"] or "")
    verbatim_quotes = _normalize_list(result.get("verbatim_quotes"))
    meta = result.get("meta")
    if not isinstance(meta, dict):
        meta = payload["meta"]
    out = {
        "kind": "l1",
        "l1_event_id": event_id,
        "timestamp": timestamp,
        "date": _date_from_timestamp(timestamp),
        "title": title or _fallback_l1_title(payload),
        "clean_text": clean_text,
        "verbatim_quotes": [str(item) for item in verbatim_quotes if str(item).strip()],
        "meta": meta,
    }
    return out


def _extract_l1_results(
    result: dict[str, Any],
    records: list[dict[str, Any]],
    paths: list[Path],
) -> list[dict[str, Any]]:
    raw_items = result.get("events") or result.get("items") or []
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list) or len(raw_items) != len(records):
        if len(records) == 1 and isinstance(result, dict):
            raw_items = [result]
        else:
            raise ValueError("L1 response must return one result per input event")

    out: list[dict[str, Any]] = []
    for item, record, path in zip(raw_items, records, paths, strict=False):
        if not isinstance(item, dict):
            raise ValueError("L1 response items must be objects")
        out.append(_normalize_l1_output(item, record, path))
    return out


def _fallback_l1_title(payload: dict[str, Any]) -> str:
    app = payload.get("meta") or {}
    app_name = None
    if isinstance(app, dict):
        app_value = app.get("app")
        if isinstance(app_value, dict):
            app_name = app_value.get("name")
    type_ = str(payload.get("type") or "event")
    if app_name:
        return f"{type_} in {app_name}"
    return type_.title()


def _l1_worker(config: ProcessorConfig, app_config: AppConfig, semaphore: multiprocessing.Semaphore) -> None:
    config.out_dir.mkdir(parents=True, exist_ok=True)
    assert config.state_dir is not None
    config.state_dir.mkdir(parents=True, exist_ok=True)

    while True:
        vault_files = sorted(config.vault_dir.glob("*.json"))
        if not vault_files:
            logging.info("L1 worker: No raw events to process. Sleeping...")
            time.sleep(config.poll_interval_seconds)
            continue

        processed_count = 0
        date_str = _utc_date()
        l1_cleaned_dir = config.out_dir / "l1_cleaned" / date_str
        l0_processed_raw_dir = config.out_dir / "l0_processed_raw" / date_str
        _ensure_parent(l1_cleaned_dir / "dummy.json") # Ensure directory exists
        _ensure_parent(l0_processed_raw_dir / "dummy.json") # Ensure directory exists

        # Only process one batch at a time within the loop for simplicity of worker logic
        # The main orchestrator will spawn multiple workers.
        batch_paths = vault_files[:config.l1_group_size]
        if not batch_paths:
            logging.info("L1 worker: No raw events to process in batch. Sleeping...")
            time.sleep(config.poll_interval_seconds)
            continue

        records = [_load_json(path) for path in batch_paths]

        llm_client = ProcessorLLMClient(app_config.llm, app_config.prompts)
        try:
            semaphore.acquire()
            result = llm_client.complete_json("l1_clean", _build_l1_batch_payload(records, batch_paths))
            l1_events = _extract_l1_results(result, records, batch_paths)

            for original_path, l1_event in zip(batch_paths, l1_events):
                event_id = l1_event["l1_event_id"]
                output_path = l1_cleaned_dir / f"{event_id}.json"
                archive_path = l0_processed_raw_dir / original_path.name

                if not config.dry_run:
                    _atomic_write_json(output_path, l1_event)
                    original_path.replace(archive_path) # Move to archive
                processed_count += 1
            logging.info(f"L1 worker: Processed {processed_count} raw events.")
        except Exception as e:
            logging.error(f"L1 worker: Error processing raw events: {e}")
        finally:
            semaphore.release()
            time.sleep(config.poll_interval_seconds) # Sleep after processing or error


def _normalize_l2_item(item: dict[str, Any], inputs: list[dict[str, Any]], source_indexes: list[int]) -> dict[str, Any]:
    source_events = [inputs[i] for i in source_indexes if 0 <= i < len(inputs)]
    timestamps = [str(event.get("timestamp") or "") for event in source_events if event.get("timestamp")]
    timestamps = [ts for ts in timestamps if ts]
    start_ts = str(item.get("timestamp_start") or (min(timestamps) if timestamps else ""))
    end_ts = str(item.get("timestamp_end") or (max(timestamps) if timestamps else start_ts))
    title = str(item.get("title") or "")
    summary = str(item.get("summary") or "")
    clean_text = str(item.get("clean_text") or "")
    event_id = str(item.get("l2_event_id") or item.get("event_id") or "")
    if not event_id:
        base = title or (source_events[0].get("title") if source_events else "event")
        event_id = f"group_{_safe_id(start_ts or _utc_iso())}_{_slugify(base)}"
    event_id = _safe_id(event_id)
    return {
        "kind": "l2",
        "l2_event_id": event_id,
        "title": title or (source_events[0].get("title") if source_events else "Event"),
        "summary": summary,
        "clean_text": clean_text,
        "timestamp_start": start_ts,
        "timestamp_end": end_ts,
        "date": _date_from_timestamp(start_ts or end_ts),
    }


def _extract_l2_groups(result: dict[str, Any], inputs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[int]]]:
    raw_items = result.get("events") or result.get("groups") or result.get("items") or []
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        raw_items = []

    groups: list[dict[str, Any]] = []
    deleted: dict[str, list[int]] = {}
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            continue
        source_indexes_raw = raw_item.get("source_indexes") or raw_item.get("indexes") or raw_item.get("source_index")
        if isinstance(source_indexes_raw, int):
            source_indexes = [source_indexes_raw]
        elif isinstance(source_indexes_raw, list):
            source_indexes = [int(i) for i in source_indexes_raw if isinstance(i, int) or (isinstance(i, str) and i.isdigit())]
        else:
            if len(raw_items) == len(inputs):
                source_indexes = [index]
            elif len(raw_items) == 1:
                source_indexes = list(range(len(inputs)))
            else:
                source_indexes = [min(index, max(0, len(inputs) - 1))]

        # The instruction states: "If the count is >= config.l2_trigger_threshold: Take a batch of config.l2_trigger_threshold files. Call the l2_group prompt on the LLM. Save the resulting correlated L2 events..."
        # This implies that the LLM is expected to return correlated groups.
        # The old logic `if len(source_indexes) < 2:` filters out single events that are not explicitly grouped.
        # Keeping this for now, assuming the LLM should group events.
        if len(source_indexes) < 2:
            continue

        normalized = _normalize_l2_item(raw_item, inputs, source_indexes)
        groups.append(normalized)
        deleted[normalized["l2_event_id"]] = source_indexes
    return groups, deleted


def _l2_worker(config: ProcessorConfig, app_config: AppConfig, semaphore: multiprocessing.Semaphore) -> None:
    config.out_dir.mkdir(parents=True, exist_ok=True)
    assert config.state_dir is not None
    config.state_dir.mkdir(parents=True, exist_ok=True)

    while True:
        l1_cleaned_files = _iter_json_files_recursive(config.out_dir / "l1_cleaned")
        if len(l1_cleaned_files) < config.l2_trigger_threshold:
            logging.info(f"L2 worker: Not enough L1 events ({len(l1_cleaned_files)}) to process. Sleeping...")
            time.sleep(config.poll_interval_seconds)
            continue

        processed_groups_count = 0
        date_str = _utc_date()
        l2_correlated_dir = config.out_dir / "l2_correlated" / date_str
        l1_processed_archive_dir = config.out_dir / "l1_processed" / date_str
        _ensure_parent(l2_correlated_dir / "dummy.json")
        _ensure_parent(l1_processed_archive_dir / "dummy.json")

        # Take a batch of files up to the trigger threshold
        batch_paths = l1_cleaned_files[: config.l2_trigger_threshold]
        if not batch_paths:
            logging.info("L2 worker: No L1 events to process in batch. Sleeping...")
            time.sleep(config.poll_interval_seconds)
            continue

        inputs = [_load_json(path) for path in batch_paths]

        llm_client = ProcessorLLMClient(app_config.llm, app_config.prompts)
        try:
            semaphore.acquire()
            result = llm_client.complete_json("l2_group", {"events": inputs})
            groups, deleted_indexes_by_group_id = _extract_l2_groups(result, inputs)

            for group in groups:
                group_id = group["l2_event_id"]
                output_path = l2_correlated_dir / f"{group_id}.json"
                if not config.dry_run:
                    _atomic_write_json(output_path, group)
                processed_groups_count += 1

                # Move consumed L1 files to archive
                source_indexes = deleted_indexes_by_group_id.get(group_id, [])
                # Iterate over the original batch_paths for deletion, not input (which are loaded JSONs)
                for idx in source_indexes:
                    if 0 <= idx < len(batch_paths):
                        original_l1_path = batch_paths[idx]
                        archive_l1_path = l1_processed_archive_dir / original_l1_path.name
                        if not config.dry_run:
                            original_l1_path.replace(archive_l1_path) # Move to archive
            logging.info(f"L2 worker: Processed {processed_groups_count} L2 groups.")
        except Exception as e:
            logging.error(f"L2 worker: Error processing L1 events: {e}")
        finally:
            semaphore.release()
            time.sleep(config.poll_interval_seconds) # Sleep after processing or error


def _merge_model(existing: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = _default_user_model()
    merged.update({k: copy.deepcopy(v) for k, v in existing.items() if k in merged})
    candidate = update.get("user_model") if isinstance(update.get("user_model"), dict) else update
    if isinstance(candidate, dict):
        for key in merged:
            if key in candidate:
                merged[key] = _normalize_list(candidate.get(key))
    merged["updated_at"] = _utc_iso()
    return merged


def _load_user_model_md(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _default_user_model()
    content = path.read_text(encoding="utf-8")
    match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
    if match:
        try:
            frontmatter = {}
            for line in match.group(1).splitlines():
                if ": " in line:
                    key, value = line.split(": ", 1)
                    frontmatter[key.strip()] = value.strip()
            return _merge_model(_default_user_model(), frontmatter)
        except Exception:
            pass
    return _default_user_model()

def _load_all_user_models_content(user_model_dir: Path) -> list[dict[str, str]]:
    models_content = []
    if user_model_dir.exists():
        for path in user_model_dir.glob("*.md"):
            models_content.append({"file_name": path.name, "content": path.read_text(encoding="utf-8")})
    return models_content


def _format_note_links(links: Any) -> list[str]:
    out: list[str] = []
    for link in _normalize_list(links):
        if not isinstance(link, str):
            continue
        cleaned = link.strip().strip("[]")
        if cleaned:
            out.append(f"[[{cleaned}]]")
    return out


def _render_note(note: dict[str, Any]) -> str:
    kind = str(note.get("kind") or note.get("type") or "topic").strip().lower()
    name = str(note.get("name") or note.get("title") or kind).strip() or kind
    summary = str(note.get("summary") or note.get("description") or "").strip()
    links = _format_note_links(note.get("links"))
    evidence = [str(item).strip() for item in _normalize_list(note.get("evidence")) if str(item).strip()]
    notes = [str(item).strip() for item in _normalize_list(note.get("notes")) if str(item).strip()]
    updated_at = str(note.get("updated_at") or _utc_iso())
    lines = [
        "---",
        f"kind: {kind}",
        f"name: {name}",
        f"updated_at: {updated_at}",
        "---",
        "",
        f"# {name}",
        "",
        "## Summary",
        summary or "No summary.",
        "",
        "## Links",
        *(links or ["(none)"]),
        "",
        "## Recent Evidence",
        *([f"- {item}" for item in evidence] or ["- (none)"]),
        "",
        "## Notes",
        *([f"- {item}" for item in notes] or ["- (none)"]),
        "",
    ]
    return "\n".join(lines)


def _note_path(notes_dir: Path, note: dict[str, Any]) -> Path:
    kind = str(note.get("kind") or note.get("type") or "topic").strip().lower()
    name = str(note.get("name") or note.get("title") or kind).strip()
    slug = _slugify(name)
    if kind == "day":
        date = str(note.get("date") or name or _utc_date())
        slug = str(date or _utc_date())
    return notes_dir / f"{kind}__{slug}.md"


def _default_day_note(date: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    titles = [str(item.get("title") or item.get("summary") or "Event").strip() for item in events if isinstance(item, dict)]
    links = []
    for event in events:
        title = str(event.get("title") or "").strip()
        if title:
            links.append(_slugify(title))
    return {
        "kind": "day",
        "date": date,
        "name": date,
        "summary": " | ".join(titles[:6]) if titles else f"Activity for {date}",
        "links": [f"topic__{slug}" for slug in links[:6]],
        "evidence": [f"- {title}" for title in titles[:8]],
        "notes": [],
    }


def _l3_worker(config: ProcessorConfig, app_config: AppConfig, semaphore: multiprocessing.Semaphore) -> None:
    config.out_dir.mkdir(parents=True, exist_ok=True)
    assert config.state_dir is not None
    config.state_dir.mkdir(parents=True, exist_ok=True)

    while True:
        l2_correlated_files = _iter_json_files_recursive(config.out_dir / "l2_correlated")
        if len(l2_correlated_files) < config.l3_trigger_threshold:
            logging.info(f"L3 worker: Not enough L2 events ({len(l2_correlated_files)}) to process. Sleeping...")
            time.sleep(config.poll_interval_seconds)
            continue

        processed_events_count = 0
        date_str = _utc_date()
        user_model_dir = config.out_dir / "user_model"
        l2_processed_archive_dir = config.out_dir / "l2_processed" / date_str
        _ensure_parent(user_model_dir / "dummy.md")
        _ensure_parent(l2_processed_archive_dir / "dummy.json")

        # Take a batch of files up to the trigger threshold
        batch_paths = l2_correlated_files[: config.l3_trigger_threshold]
        if not batch_paths:
            logging.info("L3 worker: No L2 events to process in batch. Sleeping...")
            time.sleep(config.poll_interval_seconds)
            continue

        l2_events = [_load_json(path) for path in batch_paths]
        existing_user_models_content = _load_all_user_models_content(user_model_dir)

        payload = {
            "existing_user_models": existing_user_models_content,
            "new_l2_events": l2_events
        }

        llm_client = ProcessorLLMClient(app_config.llm, app_config.prompts)
        try:
            semaphore.acquire()
            result = llm_client.complete_json("l3_user_model", payload)

            updated_user_model_notes = result.get("notes") or []
            if not isinstance(updated_user_model_notes, list):
                updated_user_model_notes = [updated_user_model_notes]

            for note in updated_user_model_notes:
                if not isinstance(note, dict):
                    continue
                note_path = _note_path(user_model_dir, note)
                rendered_note = _render_note(note)
                if not config.dry_run:
                    _atomic_write_text(note_path, rendered_note)
                processed_events_count += 1

            # Move consumed L2 files to archive
            for original_l2_path in batch_paths:
                archive_l2_path = l2_processed_archive_dir / original_l2_path.name
                if not config.dry_run:
                    original_l2_path.replace(archive_l2_path)
            logging.info(f"L3 worker: Processed {processed_events_count} L3 events.")
        except Exception as e:
            logging.error(f"L3 worker: Error processing L2 events: {e}")
        finally:
            semaphore.release()
            time.sleep(config.poll_interval_seconds) # Sleep after processing or error


def _l4_worker(config: ProcessorConfig, app_config: AppConfig, semaphore: multiprocessing.Semaphore) -> None:
    config.out_dir.mkdir(parents=True, exist_ok=True)
    assert config.state_dir is not None
    config.state_dir.mkdir(parents=True, exist_ok=True)

    while True:
        l4_state_path = config.state_dir / "l4_state.json"
        l4_state_data = _load_json_or_default(l4_state_path, {"last_run_timestamp": None})
        last_run_timestamp_str = l4_state_data.get("last_run_timestamp")

        now = _utc_now()
        should_run = False

        if last_run_timestamp_str:
            try:
                last_run_timestamp = datetime.fromisoformat(last_run_timestamp_str).replace(tzinfo=timezone.utc)
                elapsed_hours = (now - last_run_timestamp).total_seconds() / 3600
                if elapsed_hours >= config.l4_interval_hours:
                    should_run = True
            except ValueError:
                should_run = True
        else:
            should_run = True

        if not should_run:
            logging.info("L4 worker: Not scheduled to run yet. Sleeping...")
            time.sleep(config.poll_interval_seconds)
            continue

        if not config.l4_enabled:
            logging.info("L4 worker: L4 processing is disabled. Sleeping...")
            time.sleep(config.poll_interval_seconds)
            continue

        user_model_dir = config.out_dir / "user_model"
        reflection_output_dir = config.out_dir / "reflections"
        _ensure_parent(reflection_output_dir / "dummy.md")

        user_model_content = _load_all_user_models_content(user_model_dir)

        if not user_model_content:
            logging.info("L4 worker: No user model content to process. Sleeping...")
            time.sleep(config.poll_interval_seconds)
            continue

        payload = {
            "current_date": _utc_date(),
            "user_model_files": user_model_content,
        }

        llm_client = ProcessorLLMClient(app_config.llm, app_config.prompts)
        try:
            semaphore.acquire()
            reflection_text = llm_client.complete_text("l4_reflection", payload)

            if not reflection_text.strip():
                logging.info("L4 worker: LLM returned empty reflection. Sleeping...")
                time.sleep(config.poll_interval_seconds)
                continue

            output_reflection_path = reflection_output_dir / f"{_utc_date()}.md"

            if not config.dry_run:
                _atomic_write_text(output_reflection_path, reflection_text.strip() + "\n")
                l4_state_data["last_run_timestamp"] = _utc_iso()
                _atomic_write_json(l4_state_path, l4_state_data)
            logging.info("L4 worker: Generated L4 reflection.")
        except Exception as e:
            logging.error(f"L4 worker: Error generating reflection: {e}")
        finally:
            semaphore.release()
            time.sleep(config.poll_interval_seconds) # Sleep after processing or error
