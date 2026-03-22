"""Unit tests for the event -> timeline -> notes processor pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from exocort.collector.vault import normalize_vault_response
from exocort.processor import ProcessorConfig, run_once
from exocort.processor.models import PipelineDefinition, StageDefinition


pytestmark = pytest.mark.unit


class FakeProcessorLLMClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete_json(self, stage_name: str, prompt: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(stage_name)

        if stage_name == "l1":
            assert "normalized event objects" in prompt
            events = payload.get("events") if isinstance(payload.get("events"), list) else []
            rows: list[dict[str, object]] = []
            for event in events:
                if not isinstance(event, dict):
                    continue
                event_id = str(event.get("id") or "event")
                timestamp = str(event.get("timestamp") or "2026-03-19T10:00:00+00:00")
                rows.append(
                    {
                        "event_id": event_id,
                        "timestamp": timestamp,
                        "date": timestamp[:10],
                        "title": f"Event {event_id}",
                        "description": f"Observed activity for {event_id}.",
                        "content": json.dumps(event, ensure_ascii=False),
                        "meta": event.get("meta") or {},
                        "source_type": str(event.get("type") or "screen"),
                        "source_raw_event_id": event_id,
                    }
                )
            return {"events": rows}

        if stage_name == "l2":
            assert "cleaned timeline" in prompt
            events = payload.get("events") if isinstance(payload.get("events"), list) else []
            if not events:
                return {"cleaned_timeline": [], "super_events": []}

            first = events[0] if isinstance(events[0], dict) else {}
            last = events[-1] if isinstance(events[-1], dict) else first
            event_ids = [str(event.get("event_id") or "") for event in events if isinstance(event, dict)]
            start_ts = str(first.get("timestamp") or "2026-03-19T10:00:00+00:00")
            end_ts = str(last.get("timestamp") or start_ts)
            date = start_ts[:10]

            if len(events) >= 2:
                return {
                    "cleaned_timeline": [
                        {
                            "timeline_event_id": "timeline_focus_block",
                            "title": "OCR parser work",
                            "description": "Focused work block on OCR parser improvements.",
                            "timestamp_start": start_ts,
                            "timestamp_end": end_ts,
                            "date": date,
                            "source_event_ids": event_ids,
                            "super_event_id": "super_focus_block",
                        }
                    ],
                    "super_events": [
                        {
                            "super_event_id": "super_focus_block",
                            "title": "OCR parser work",
                            "description": "Grouped OCR parser work session.",
                            "timestamp_start": start_ts,
                            "timestamp_end": end_ts,
                            "date": date,
                            "source_event_ids": event_ids,
                            "timeline_event_ids": ["timeline_focus_block"],
                            "grouping_dimensions": ["topic", "process"],
                            "category": "work",
                            "subject": "ocr-parser",
                        }
                    ],
                }

            return {
                "cleaned_timeline": [
                    {
                        "timeline_event_id": f"timeline_{event_ids[0]}",
                        "title": "Single activity",
                        "description": "Single event preserved in the cleaned timeline.",
                        "timestamp_start": start_ts,
                        "timestamp_end": end_ts,
                        "date": date,
                        "source_event_ids": event_ids,
                        "super_event_id": f"super_{event_ids[0]}",
                    }
                ],
                "super_events": [
                    {
                        "super_event_id": f"super_{event_ids[0]}",
                        "title": "Single activity",
                        "description": "Single event converted into a super event.",
                        "timestamp_start": start_ts,
                        "timestamp_end": end_ts,
                        "date": date,
                        "source_event_ids": event_ids,
                        "timeline_event_ids": [f"timeline_{event_ids[0]}"],
                        "grouping_dimensions": ["topic"],
                        "category": "activity",
                        "subject": event_ids[0],
                    }
                ],
            }

        if stage_name == "l3":
            assert "inbox notes" in prompt
            super_events = payload.get("super_events") if isinstance(payload.get("super_events"), list) else []
            notes: list[dict[str, object]] = []
            for super_event in super_events:
                if not isinstance(super_event, dict):
                    continue
                super_event_id = str(super_event.get("super_event_id") or "super_event")
                notes.append(
                    {
                        "note_id": f"note_{super_event_id}",
                        "timestamp": str(super_event.get("timestamp_start") or ""),
                        "date": str(super_event.get("date") or "2026-03-19"),
                        "title": str(super_event.get("title") or "Untitled note"),
                        "description": str(super_event.get("description") or ""),
                        "content": f"Derived note for {super_event_id}.",
                        "category": str(super_event.get("category") or ""),
                        "subject": str(super_event.get("subject") or ""),
                        "super_event_id": super_event_id,
                        "source_event_ids": super_event.get("source_event_ids") or [],
                    }
                )
            return {"notes": notes}

        raise AssertionError(f"unexpected stage name {stage_name!r}")


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_raw_record(
    vault_dir: Path,
    *,
    date: str,
    timestamp_iso: str,
    event_id: str,
    raw_text: str,
) -> Path:
    day_dir = vault_dir / date
    day_dir.mkdir(parents=True, exist_ok=True)
    safe_ts = timestamp_iso.replace(":", "-")
    path = day_dir / f"{safe_ts}_screen_{event_id}.json"
    path.write_text(
        json.dumps(
            {
                "timestamp": timestamp_iso,
                "type": "screen",
                "id": event_id,
                "meta": {"app": {"name": "Cursor"}, "window": {"title": "openai.py"}},
                "responses": [
                    normalize_vault_response(
                        "http://127.0.0.1:9093/ocr",
                        "openai",
                        True,
                        200,
                        raw_text,
                        raw_text,
                    )
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def build_processor_config(vault_dir: Path, out_dir: Path, execution_mode: str = "per_stage_worker") -> ProcessorConfig:
    return ProcessorConfig(
        vault_dir=vault_dir,
        out_dir=out_dir,
        state_dir=out_dir / "state",
        poll_interval_s=1,
        max_concurrent_tasks=1,
        dry_run=False,
        pipeline=PipelineDefinition(
            execution_mode=execution_mode,  # type: ignore[arg-type]
            stages=[
                StageDefinition(
                    name="l1",
                    type="llm_map",
                    input={"base_dir": "vault", "path": ".", "format": "json"},
                    outputs=[
                        {
                            "name": "events",
                            "collection": {"base_dir": "out", "path": "l1", "format": "json"},
                            "projection": "none",
                            "result_key": "events",
                            "kind": "event",
                            "id_field": "event_id",
                            "date_field": "date",
                            "timestamp_field": "timestamp",
                            "source_id_field": "source_raw_event_id",
                        }
                    ],
                    enabled=True,
                    state_key="l1",
                    prompt="You transform raw capturer records into normalized event objects.",
                    batch_size=2,
                    flush_threshold=2,
                    flush_when_upstream_empty=True,
                    upstream=[],
                    archive={"base_dir": "out", "path": "l0_processed_raw", "format": "json"},
                    transform_adapter="llm_map",
                    transform_options={"input_mode": "raw", "input_key": "events"},
                    concurrency=1,
                ),
                StageDefinition(
                    name="l2",
                    type="llm_reduce",
                    input={"base_dir": "out", "path": "l1", "format": "json"},
                    outputs=[
                        {
                            "name": "timeline_events",
                            "collection": {"base_dir": "out", "path": "timeline_events", "format": "json"},
                            "projection": "jsonl_day",
                            "projection_target": {"base_dir": "out", "path": "timeline", "format": "jsonl"},
                            "result_key": "cleaned_timeline",
                            "kind": "timeline_event",
                            "id_field": "timeline_event_id",
                            "date_field": "date",
                            "timestamp_field": "timestamp_start",
                            "source_id_field": "source_event_ids",
                        },
                        {
                            "name": "super_events",
                            "collection": {"base_dir": "out", "path": "l2", "format": "json"},
                            "projection": "none",
                            "result_key": "super_events",
                            "kind": "super_event",
                            "id_field": "super_event_id",
                            "date_field": "date",
                            "timestamp_field": "timestamp_start",
                            "source_id_field": "source_event_ids",
                        },
                    ],
                    enabled=True,
                    state_key="l2",
                    prompt="You transform normalized events into a cleaned timeline and grouped super-events.",
                    batch_size=2,
                    flush_threshold=2,
                    flush_when_upstream_empty=True,
                    upstream=[{"base_dir": "vault", "path": ".", "format": "json"}],
                    archive={"base_dir": "out", "path": "l1_processed", "format": "json"},
                    transform_adapter="llm_reduce",
                    transform_options={"input_mode": "payload", "input_key": "events"},
                    concurrency=1,
                ),
                StageDefinition(
                    name="l3",
                    type="llm_reduce",
                    input={"base_dir": "out", "path": "l2", "format": "json"},
                    outputs=[
                        {
                            "name": "notes",
                            "collection": {"base_dir": "out", "path": "notes", "format": "json"},
                            "projection": "none",
                            "result_key": "notes",
                            "kind": "inbox_note",
                            "id_field": "note_id",
                            "date_field": "date",
                            "timestamp_field": "timestamp",
                            "source_id_field": "source_event_ids",
                        },
                        {
                            "name": "note_docs",
                            "collection": {"base_dir": "out", "path": "notes/inbox", "format": "markdown"},
                            "projection": "markdown_note",
                            "result_key": "notes",
                            "kind": "inbox_note",
                            "id_field": "note_id",
                            "date_field": "date",
                            "timestamp_field": "timestamp",
                            "source_id_field": "source_event_ids",
                        },
                    ],
                    enabled=True,
                    state_key="l3",
                    prompt="You transform super-events into inbox notes.",
                    batch_size=1,
                    flush_threshold=1,
                    flush_when_upstream_empty=True,
                    upstream=[{"base_dir": "out", "path": "l1", "format": "json"}],
                    archive=None,
                    transform_adapter="llm_reduce",
                    transform_options={"input_mode": "payload", "input_key": "super_events"},
                    concurrency=1,
                ),
            ],
        ),
    )


@pytest.mark.parametrize("execution_mode", ["per_stage_worker", "single_loop"])
def test_processor_creates_super_events_and_notes_from_related_events(
    tmp_path: Path,
    execution_mode: str,
) -> None:
    vault_dir = tmp_path / "vault"
    out_dir = tmp_path / "processed"

    record_a = write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:00:00+00:00",
        event_id="screen_event_a",
        raw_text="raw OCR text A",
    )
    record_b = write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:01:00+00:00",
        event_id="screen_event_b",
        raw_text="raw OCR text B",
    )

    config = build_processor_config(vault_dir, out_dir, execution_mode=execution_mode)
    client = FakeProcessorLLMClient()

    processed = run_once(config, client=client)

    assert processed == 5
    assert not record_a.exists()
    assert not record_b.exists()
    assert client.calls == ["l1", "l2", "l3"]

    timeline_path = out_dir / "timeline" / "2026-03-19.jsonl"
    super_event_path = out_dir / "l2" / "2026-03-19" / "super_focus_block.json"
    note_path = out_dir / "notes" / "inbox" / "2026-03-19" / "note_super_focus_block.md"
    note_json_path = out_dir / "notes" / "2026-03-19" / "note_super_focus_block.json"
    l1_archive_a = out_dir / "l0_processed_raw" / "2026-03-19" / record_a.name
    l1_archive_b = out_dir / "l0_processed_raw" / "2026-03-19" / record_b.name
    l2_archive_a = out_dir / "l1_processed" / "2026-03-19" / "screen_event_a.json"
    l2_archive_b = out_dir / "l1_processed" / "2026-03-19" / "screen_event_b.json"

    assert timeline_path.exists()
    assert super_event_path.exists()
    assert note_path.exists()
    assert note_json_path.exists()
    assert l1_archive_a.exists()
    assert l1_archive_b.exists()
    assert l2_archive_a.exists()
    assert l2_archive_b.exists()

    timeline_lines = [json.loads(line) for line in timeline_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(timeline_lines) == 1
    assert timeline_lines[0]["super_event_id"] == "super_focus_block"
    assert timeline_lines[0]["source_event_ids"] == ["screen_event_a", "screen_event_b"]

    super_event = load_json(super_event_path)
    assert super_event["payload"]["grouping_dimensions"] == ["topic", "process"]
    assert super_event["payload"]["category"] == "work"

    note_text = note_path.read_text(encoding="utf-8")
    assert 'item_id: "note_super_focus_block"' in note_text
    assert 'stage: "l3"' in note_text


def test_processor_flushes_single_event_into_super_event_when_upstream_is_empty(
    tmp_path: Path,
) -> None:
    vault_dir = tmp_path / "vault"
    out_dir = tmp_path / "processed"

    record = write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T12:00:00+00:00",
        event_id="screen_event_single",
        raw_text="raw OCR text single",
    )

    config = build_processor_config(vault_dir, out_dir)
    config.pipeline.stages[0].batch_size = 1
    config.pipeline.stages[0].flush_threshold = 1
    config.pipeline.stages[1].batch_size = 3
    config.pipeline.stages[1].flush_threshold = 3
    config.pipeline.stages[2].batch_size = 2
    config.pipeline.stages[2].flush_threshold = 2
    client = FakeProcessorLLMClient()

    processed = run_once(config, client=client)

    assert processed == 4
    assert not record.exists()

    timeline_path = out_dir / "timeline" / "2026-03-19.jsonl"
    super_event_path = out_dir / "l2" / "2026-03-19" / "super_screen_event_single.json"
    note_path = out_dir / "notes" / "inbox" / "2026-03-19" / "note_super_screen_event_single.md"

    assert timeline_path.exists()
    assert super_event_path.exists()
    assert note_path.exists()

    timeline_lines = [json.loads(line) for line in timeline_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(timeline_lines) == 1
    assert timeline_lines[0]["source_event_ids"] == ["screen_event_single"]


def test_processor_levels_progress_across_runs_without_reprocessing_old_super_events(
    tmp_path: Path,
) -> None:
    vault_dir = tmp_path / "vault"
    out_dir = tmp_path / "processed"

    write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:00:00+00:00",
        event_id="screen_event_a",
        raw_text="raw OCR text A",
    )
    write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:01:00+00:00",
        event_id="screen_event_b",
        raw_text="raw OCR text B",
    )
    write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T10:02:00+00:00",
        event_id="screen_event_c",
        raw_text="raw OCR text C",
    )

    config = build_processor_config(vault_dir, out_dir)
    client = FakeProcessorLLMClient()

    first_pass = run_once(config, client=client)
    second_pass = run_once(config, client=client)

    assert first_pass == 5
    assert second_pass == 4

    note_dir = out_dir / "notes" / "inbox" / "2026-03-19"
    notes = sorted(path.name for path in note_dir.glob("*.md"))
    assert notes == ["note_super_focus_block.md", "note_super_screen_event_c.md"]

    state_l3 = load_json(out_dir / "state" / "state_l3.json")
    assert state_l3["cursor_id"] == "super_screen_event_c"


def test_processor_supports_generic_llm_pipeline_with_free_payload(
    tmp_path: Path,
) -> None:
    vault_dir = tmp_path / "vault"
    out_dir = tmp_path / "processed"
    write_raw_record(
        vault_dir,
        date="2026-03-19",
        timestamp_iso="2026-03-19T09:00:00+00:00",
        event_id="screen_event_generic",
        raw_text="generic payload text",
    )

    class GenericClient:
        def complete_json(self, stage_name: str, prompt: str, payload: dict[str, object]) -> dict[str, object]:
            assert stage_name == "generic_stage"
            assert prompt == "Return one custom summary per record."
            assert "records" in payload
            return {
                "items": [
                    {
                        "id": "generic_item",
                        "date": "2026-03-19",
                        "timestamp": "2026-03-19T09:00:00+00:00",
                        "title": "Custom title",
                        "description": "Custom description",
                        "source_ids": ["screen_event_generic"],
                    }
                ]
            }

    config = ProcessorConfig(
        vault_dir=vault_dir,
        out_dir=out_dir,
        state_dir=out_dir / "state",
        poll_interval_s=1,
        max_concurrent_tasks=1,
        dry_run=False,
        pipeline=PipelineDefinition(
            execution_mode="single_loop",
            stages=[
                StageDefinition(
                    name="generic_stage",
                    type="llm_map",
                    input={"base_dir": "vault", "path": ".", "format": "json"},
                    outputs=[
                        {
                            "name": "items",
                            "collection": {"base_dir": "out", "path": "custom", "format": "json"},
                            "projection": "none",
                            "result_key": "items",
                            "kind": "custom_summary",
                            "id_field": "id",
                            "date_field": "date",
                            "timestamp_field": "timestamp",
                            "source_id_field": "source_ids",
                        }
                    ],
                    enabled=True,
                    state_key="generic_stage",
                    prompt="Return one custom summary per record.",
                    batch_size=1,
                    flush_threshold=1,
                    flush_when_upstream_empty=True,
                    upstream=[],
                    archive=None,
                    transform_adapter="llm_map",
                    transform_options={"input_mode": "raw", "input_key": "records"},
                    concurrency=1,
                )
            ],
        ),
    )

    processed = run_once(config, client=GenericClient())

    assert processed == 1
    artifact = load_json(out_dir / "custom" / "2026-03-19" / "generic_item.json")
    assert artifact["kind"] == "custom_summary"
    assert artifact["payload"]["title"] == "Custom title"
