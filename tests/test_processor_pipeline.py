"""Unit tests for the layered processor pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from exocort.collector.vault import normalize_vault_response, write_vault_record
from exocort.processor import ProcessorConfig, run_once
from exocort.processor import engine as processor_engine


pytestmark = pytest.mark.unit


class FakeProcessorLLMClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete_json(self, prompt_key: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(prompt_key)
        if prompt_key == "l1_clean":
            events = payload.get("events") if isinstance(payload.get("events"), list) else [payload]
            cleaned_events: list[dict[str, object]] = []
            for event in events:
                if not isinstance(event, dict):
                    continue
                raw_event_id = str(event.get("raw_event_id") or event.get("id") or "event")
                title = str(event.get("raw_text") or raw_event_id).strip() or raw_event_id
                cleaned_events.append(
                    {
                        "l1_event_id": raw_event_id,
                        "timestamp": str(event.get("timestamp") or "2026-03-19T10:00:00+00:00"),
                        "title": f"Cleaned {title}",
                        "clean_text": f"Cleaned text for {raw_event_id}.",
                        "verbatim_quotes": [f"quote from {raw_event_id}"],
                        "meta": event.get("meta") or {},
                    }
                )
            return {"events": cleaned_events}
        if prompt_key == "l2_group":
            events = payload.get("events") if isinstance(payload.get("events"), list) else []
            if len(events) < 2:
                return {"events": []}
            source_indexes = list(range(len(events)))
            first = events[0] if events else {}
            last = events[-1] if events else first
            start_ts = str(first.get("timestamp") or first.get("timestamp_start") or "2026-03-19T10:00:00+00:00")
            end_ts = str(last.get("timestamp") or last.get("timestamp_end") or start_ts)
            return {
                "events": [
                    {
                        "event_id": "group_2026-03-19T10-00",
                        "title": "Grouped OCR work",
                        "summary": "Grouped edits around OCR parsing.",
                        "clean_text": "Consolidated OCR work.",
                        "timestamp_start": start_ts,
                        "timestamp_end": end_ts,
                        "source_indexes": source_indexes,
                    }
                ]
            }
        if prompt_key == "l3_profile":
            return {
                "user_model": {
                    "skills": [{"name": "Python", "confidence": 0.8}],
                    "domains": [{"name": "Developer tooling"}],
                    "projects": [{"name": "exocort", "status": "active"}],
                    "tools": [{"name": "Cursor"}],
                    "interests": [],
                    "preferences": [],
                    "people": [],
                    "orgs": [],
                    "open_questions": [],
                },
                "notes": [
                    {
                        "kind": "topic",
                        "name": "OCR",
                        "summary": "Working on OCR parser",
                        "links": ["project__exocort"],
                        "evidence": ["2026-03-19: Cleaned OCR parser"],
                        "notes": ["Pending review"],
                    }
                ],
            }
        raise AssertionError(f"unexpected prompt key {prompt_key!r}")

    def complete_text(self, prompt_key: str, payload: dict[str, object]) -> str:
        self.calls.append(prompt_key)
        return "# Reflections\n\n- Keep iterating on OCR.\n"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_raw_record(
    vault_dir: Path,
    *,
    date: str,
    timestamp_iso: str,
    event_id: str,
    raw_text: str,
) -> Path:
    return write_vault_record(
        date=date,
        timestamp_iso=timestamp_iso,
        type_="screen",
        id_=event_id,
        meta={"app": {"name": "Cursor"}, "window": {"title": "openai.py"}},
        responses=[
            normalize_vault_response(
                "http://127.0.0.1:9093/ocr",
                "openai",
                True,
                200,
                raw_text,
                raw_text,
            )
        ],
    )


def test_processor_batches_l1_and_compacts_grouped_l1_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vault_dir = tmp_path / "vault"
    out_dir = tmp_path / "processed"
    monkeypatch.setenv("COLLECTOR_VAULT_DIR", str(vault_dir))

    record_a = _write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:00:00+00:00",
        event_id="screen_event_a",
        raw_text="raw OCR text A",
    )
    record_b = _write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:01:00+00:00",
        event_id="screen_event_b",
        raw_text="raw OCR text B",
    )
    record_c = _write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:02:00+00:00",
        event_id="screen_event_c",
        raw_text="raw OCR text C",
    )

    config = ProcessorConfig(
        vault_dir=vault_dir,
        out_dir=out_dir,
        state_dir=out_dir / "state",
        batch_size=10,
        poll_interval_s=1.0,
        write_notes=False,
        dry_run=False,
        l1_batch_events=2,
        l2_batch_events=2,
        l3_batch_events=10,
        l4_enabled=False,
    )
    client = FakeProcessorLLMClient()

    processed = run_once(config, client=client)

    assert processed == 4
    assert not record_a.exists()
    assert not record_b.exists()
    assert record_c.exists()

    l1_dir = out_dir / "l1" / "2026-03-19"
    l2_dir = out_dir / "l2" / "2026-03-19"
    timeline_path = out_dir / "timeline" / "2026-03-19.jsonl"
    state_l1 = out_dir / "state" / "state_l1.json"
    state_l2 = out_dir / "state" / "state_l2.json"

    assert list(l1_dir.glob("*.json")) == []
    assert not (l1_dir / "screen_event_a.json").exists()
    assert not (l1_dir / "screen_event_b.json").exists()
    assert record_c.exists()

    l2_path = l2_dir / "group_2026-03-19T10-00.json"
    assert l2_path.exists()
    assert timeline_path.exists()
    assert state_l1.exists()
    assert state_l2.exists()

    l2_data = _load_json(l2_path)
    assert l2_data["summary"] == "Grouped edits around OCR parsing."
    assert l2_data["timestamp_start"] == "2026-03-19T10:00:00+00:00"

    timeline_lines = [line for line in timeline_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(timeline_lines) == 1
    timeline_entry = json.loads(timeline_lines[0])
    assert timeline_entry["event_id"] == "group_2026-03-19T10-00"
    assert timeline_entry["title"] == "Grouped OCR work"

    state_l1_data = _load_json(state_l1)
    state_l2_data = _load_json(state_l2)
    assert state_l1_data["last_raw_path"] == str(record_b.resolve())
    assert state_l2_data["last_l1_path"] == str((l1_dir / "screen_event_b.json").resolve())


def test_processor_waits_for_full_l2_batch_before_grouping(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vault_dir = tmp_path / "vault"
    out_dir = tmp_path / "processed"
    monkeypatch.setenv("COLLECTOR_VAULT_DIR", str(vault_dir))

    first_record = _write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T11:00:00+00:00",
        event_id="screen_event_1",
        raw_text="raw OCR text 1",
    )
    second_record = _write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T11:01:00+00:00",
        event_id="screen_event_2",
        raw_text="raw OCR text 2",
    )

    config = ProcessorConfig(
        vault_dir=vault_dir,
        out_dir=out_dir,
        state_dir=out_dir / "state",
        batch_size=10,
        poll_interval_s=1.0,
        write_notes=False,
        dry_run=False,
        l1_batch_events=1,
        l2_batch_events=2,
        l3_batch_events=10,
        l4_enabled=False,
    )
    client = FakeProcessorLLMClient()

    first_pass = run_once(config, client=client)

    assert first_pass == 2
    assert not first_record.exists()
    assert second_record.exists()
    assert not (out_dir / "l2" / "2026-03-19").exists()
    first_timeline = out_dir / "timeline" / "2026-03-19.jsonl"
    assert first_timeline.exists()
    first_timeline_lines = [line for line in first_timeline.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(first_timeline_lines) == 1
    assert json.loads(first_timeline_lines[0])["kind"] == "l1"

    second_pass = run_once(config, client=client)

    assert second_pass == 3
    assert not second_record.exists()

    l1_dir = out_dir / "l1" / "2026-03-19"
    l2_path = out_dir / "l2" / "2026-03-19" / "group_2026-03-19T10-00.json"
    timeline_path = out_dir / "timeline" / "2026-03-19.jsonl"

    assert list(l1_dir.glob("*.json")) == []
    assert l2_path.exists()
    assert timeline_path.exists()

    timeline_lines = [line for line in timeline_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(timeline_lines) == 1
    timeline_entry = json.loads(timeline_lines[0])
    assert timeline_entry["event_id"] == "group_2026-03-19T10-00"
    assert timeline_entry["title"] == "Grouped OCR work"


def test_processor_pipeline_creates_l1_l2_notes_and_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vault_dir = tmp_path / "vault"
    out_dir = tmp_path / "processed"
    monkeypatch.setenv("COLLECTOR_VAULT_DIR", str(vault_dir))

    record_a = _write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:00:00+00:00",
        event_id="screen_event_1",
        raw_text="raw OCR text 1",
    )
    record_b = _write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:01:00+00:00",
        event_id="screen_event_2",
        raw_text="raw OCR text 2",
    )

    config = ProcessorConfig(
        vault_dir=vault_dir,
        out_dir=out_dir,
        state_dir=out_dir / "state",
        batch_size=10,
        poll_interval_s=1.0,
        write_notes=True,
        dry_run=False,
        l1_batch_events=2,
        l2_batch_events=2,
        l3_batch_events=10,
        l4_enabled=False,
    )
    client = FakeProcessorLLMClient()

    processed = run_once(config, client=client)

    assert processed == 4
    assert not record_a.exists()
    assert not record_b.exists()
    assert client.calls[:3] == ["l1_clean", "l2_group", "l3_profile"]

    l2_path = out_dir / "l2" / "2026-03-19" / "group_2026-03-19T10-00.json"
    timeline_path = out_dir / "timeline" / "2026-03-19.jsonl"
    user_model_path = out_dir / "user_model.json"
    note_path = out_dir / "notes" / "topic__ocr.md"
    day_note_path = out_dir / "notes" / "day__2026-03-19.md"
    state_l1 = out_dir / "state" / "state_l1.json"
    state_l2 = out_dir / "state" / "state_l2.json"
    state_l3 = out_dir / "state" / "state_l3.json"

    l1_dir = out_dir / "l1" / "2026-03-19"
    assert list(l1_dir.glob("*.json")) == []
    assert l2_path.exists()
    assert timeline_path.exists()
    assert user_model_path.exists()
    assert note_path.exists()
    assert day_note_path.exists()
    assert state_l1.exists()
    assert state_l2.exists()
    assert state_l3.exists()

    l2_data = _load_json(l2_path)
    assert l2_data["summary"] == "Grouped edits around OCR parsing."
    assert l2_data["timestamp_start"] == "2026-03-19T10:00:00+00:00"

    model = _load_json(user_model_path)
    assert model["skills"][0]["name"] == "Python"
    assert model["projects"][0]["name"] == "exocort"

    note_text = note_path.read_text(encoding="utf-8")
    assert "[[project__exocort]]" in note_text
    assert "Working on OCR parser" in note_text

    timeline_lines = [line for line in timeline_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(timeline_lines) == 1
    assert json.loads(timeline_lines[0])["event_id"] == "group_2026-03-19T10-00"

    state_l3_data = _load_json(state_l3)
    assert state_l3_data["last_timeline_event_key"] == "2026-03-19:group_2026-03-19T10-00"


def test_l3_consumes_effective_timeline_snapshot_including_remaining_l1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vault_dir = tmp_path / "vault"
    out_dir = tmp_path / "processed"
    monkeypatch.setenv("COLLECTOR_VAULT_DIR", str(vault_dir))

    _write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:00:00+00:00",
        event_id="screen_event_a",
        raw_text="raw OCR text A",
    )
    _write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:01:00+00:00",
        event_id="screen_event_b",
        raw_text="raw OCR text B",
    )
    _write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:02:00+00:00",
        event_id="screen_event_c",
        raw_text="raw OCR text C",
    )

    config = ProcessorConfig(
        vault_dir=vault_dir,
        out_dir=out_dir,
        state_dir=out_dir / "state",
        write_notes=False,
        dry_run=False,
        l1_batch_events=2,
        l2_batch_events=2,
        l3_batch_events=10,
        l4_enabled=False,
    )
    client = FakeProcessorLLMClient()

    first_pass = run_once(config, client=client)

    assert first_pass == 4

    second_pass = run_once(config, client=client)

    assert second_pass == 2
    state_l3 = _load_json(out_dir / "state" / "state_l3.json")
    assert state_l3["last_timeline_event_key"] == "2026-03-19:screen_event_c"

    timeline_lines = [line for line in (out_dir / "timeline" / "2026-03-19.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(timeline_lines) == 2
    entries = [json.loads(line) for line in timeline_lines]
    assert entries[0]["event_id"] == "group_2026-03-19T10-00"
    assert entries[1]["event_id"] == "screen_event_c"


def test_l4_writes_reflection_and_persists_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vault_dir = tmp_path / "vault"
    out_dir = tmp_path / "processed"
    fixed_now = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(processor_engine, "_utc_now", lambda: fixed_now)
    monkeypatch.setattr(processor_engine, "_utc_date", lambda: "2026-03-19")

    config = ProcessorConfig(
        vault_dir=vault_dir,
        out_dir=out_dir,
        state_dir=out_dir / "state",
        write_notes=False,
        dry_run=False,
        l4_enabled=True,
        l4_interval_h=24.0,
    )
    client = FakeProcessorLLMClient()

    processed = run_once(config, client=client)

    assert processed == 1
    reflection_path = out_dir / "reflections" / "2026-03-19.md"
    state_l4 = out_dir / "state" / "state_l4.json"
    assert reflection_path.exists()
    assert state_l4.exists()
    assert "l4_reflect" in client.calls

    state_data = _load_json(state_l4)
    assert state_data["last_day_processed"] == "2026-03-19"
    assert state_data["updated_at"] == fixed_now.isoformat()


def test_l4_respects_interval_and_same_day_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vault_dir = tmp_path / "vault"
    out_dir = tmp_path / "processed"
    state_dir = out_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    client = FakeProcessorLLMClient()

    monkeypatch.setattr(processor_engine, "_utc_now", lambda: datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(processor_engine, "_utc_date", lambda: "2026-03-19")

    (state_dir / "state_l4.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-03-19T11:00:00+00:00",
                "last_day_processed": None,
            }
        ),
        encoding="utf-8",
    )
    config = ProcessorConfig(
        vault_dir=vault_dir,
        out_dir=out_dir,
        state_dir=state_dir,
        write_notes=False,
        dry_run=False,
        l4_enabled=True,
        l4_interval_h=24.0,
    )

    processed = run_once(config, client=client)

    assert processed == 0
    assert "l4_reflect" not in client.calls
    assert not (out_dir / "reflections" / "2026-03-19.md").exists()

    client.calls.clear()
    (state_dir / "state_l4.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-03-18T00:00:00+00:00",
                "last_day_processed": "2026-03-19",
            }
        ),
        encoding="utf-8",
    )

    processed_same_day = run_once(config, client=client)

    assert processed_same_day == 0
    assert "l4_reflect" not in client.calls
