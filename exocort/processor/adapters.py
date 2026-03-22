"""Stage adapters for the declarative processor runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import ArtifactEnvelope, OutputDefinition, ProcessorConfig, StageDefinition
from .utils import date_from_timestamp, normalize_list, safe_id


@dataclass
class InputItem:
    path: Path
    raw: dict[str, Any]
    envelope: ArtifactEnvelope | None = None


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    out = value.strip()
    if not out:
        raise ValueError(f"{label} must not be empty")
    return out


def _input_payload(item: InputItem, mode: str) -> Any:
    if mode == "raw":
        return item.raw
    if mode == "payload":
        if item.envelope is None:
            raise ValueError("payload input_mode requires artifact inputs")
        return item.envelope.payload
    if mode == "envelope":
        if item.envelope is None:
            raise ValueError("envelope input_mode requires artifact inputs")
        return item.envelope.to_dict()
    raise ValueError(f"Unsupported input_mode {mode!r}")


def _result_rows(result: dict[str, Any], result_key: str, label: str) -> list[dict[str, Any]]:
    values = result.get(result_key)
    if not isinstance(values, list):
        raise ValueError(f"{label} expected response key {result_key!r} to be a list")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        rows.append(_require_dict(item, f"{label}.{result_key}[{index}]"))
    return rows


def _source_ids(row: dict[str, Any], output: OutputDefinition, label: str) -> list[str]:
    if output.source_id_field is None:
        return []
    values = normalize_list(row.get(output.source_id_field))
    source_ids = [str(value).strip() for value in values if str(value).strip()]
    if not source_ids:
        raise ValueError(f"{label} is missing source ids in field {output.source_id_field!r}")
    return source_ids


def _build_envelope(
    *,
    stage: StageDefinition,
    output: OutputDefinition,
    row: dict[str, Any],
    source_paths: list[str],
    index: int,
) -> ArtifactEnvelope:
    item_id = safe_id(_require_str(row.get(output.id_field), f"{stage.name}.{output.name}[{index}].{output.id_field}"))
    timestamp = _require_str(
        row.get(output.timestamp_field),
        f"{stage.name}.{output.name}[{index}].{output.timestamp_field}",
    )
    date = _require_str(row.get(output.date_field), f"{stage.name}.{output.name}[{index}].{output.date_field}")
    return ArtifactEnvelope(
        kind=output.kind,
        stage=stage.name,
        item_id=item_id,
        date=date,
        payload=row,
        timestamp=timestamp,
        source_ids=_source_ids(row, output, f"{stage.name}.{output.name}[{index}]"),
        source_paths=source_paths,
        trace={"adapter": stage.transform_adapter, "output": output.name},
    )


def _execute_llm(
    stage: StageDefinition,
    items: list[InputItem],
    client: Any,
    *,
    expect_per_input: bool,
) -> dict[str, list[ArtifactEnvelope]]:
    if stage.prompt is None:
        raise ValueError(f"Stage {stage.name} requires prompt")
    options = stage.transform_options
    input_mode = _require_str(options.get("input_mode"), f"{stage.name}.transform_options.input_mode")
    input_key = _require_str(options.get("input_key"), f"{stage.name}.transform_options.input_key")
    payload = {input_key: [_input_payload(item, input_mode) for item in items]}
    result = _require_dict(client.complete_json(stage.name, stage.prompt, payload), f"{stage.name}.response")

    outputs: dict[str, list[ArtifactEnvelope]] = {}
    shared_source_paths = [str(item.path) for item in items]
    for output in stage.outputs:
        rows = _result_rows(result, output.result_key, stage.name)
        if expect_per_input and len(rows) != len(items):
            raise ValueError(f"Stage {stage.name} expected one row in {output.result_key!r} per input item")
        output_source_paths = shared_source_paths if not expect_per_input else []
        envelopes: list[ArtifactEnvelope] = []
        for index, row in enumerate(rows):
            source_paths = output_source_paths or [str(items[index].path)]
            envelopes.append(
                _build_envelope(
                    stage=stage,
                    output=output,
                    row=row,
                    source_paths=source_paths,
                    index=index,
                )
            )
        outputs[output.name] = envelopes
    return outputs


def execute_generic_llm_map(
    stage: StageDefinition,
    items: list[InputItem],
    client: Any,
) -> dict[str, list[ArtifactEnvelope]]:
    return _execute_llm(stage, items, client, expect_per_input=True)


def execute_generic_llm_reduce(
    stage: StageDefinition,
    items: list[InputItem],
    client: Any,
) -> dict[str, list[ArtifactEnvelope]]:
    return _execute_llm(stage, items, client, expect_per_input=False)


def execute_deterministic_map(
    stage: StageDefinition,
    items: list[InputItem],
) -> dict[str, list[ArtifactEnvelope]]:
    input_mode = _require_str(stage.transform_options.get("input_mode"), f"{stage.name}.transform_options.input_mode")
    outputs: dict[str, list[ArtifactEnvelope]] = {}
    for output in stage.outputs:
        envelopes: list[ArtifactEnvelope] = []
        for index, item in enumerate(items):
            row = _require_dict(_input_payload(item, input_mode), f"{stage.name}.input[{index}]")
            envelopes.append(
                _build_envelope(
                    stage=stage,
                    output=output,
                    row=row,
                    source_paths=[str(item.path)],
                    index=index,
                )
            )
        outputs[output.name] = envelopes
    return outputs


def execute_deterministic_reduce(
    stage: StageDefinition,
    items: list[InputItem],
) -> dict[str, list[ArtifactEnvelope]]:
    options = stage.transform_options
    input_mode = _require_str(options.get("input_mode"), f"{stage.name}.transform_options.input_mode")
    payload_key = _require_str(options.get("payload_key"), f"{stage.name}.transform_options.payload_key")
    item_id = safe_id(_require_str(options.get("item_id"), f"{stage.name}.transform_options.item_id"))
    timestamp = _require_str(options.get("timestamp"), f"{stage.name}.transform_options.timestamp")
    payload = {payload_key: [_input_payload(item, input_mode) for item in items]}
    source_paths = [str(item.path) for item in items]

    outputs: dict[str, list[ArtifactEnvelope]] = {}
    for output in stage.outputs:
        outputs[output.name] = [
            ArtifactEnvelope(
                kind=output.kind,
                stage=stage.name,
                item_id=item_id,
                date=date_from_timestamp(timestamp),
                payload=payload,
                timestamp=timestamp,
                source_ids=[],
                source_paths=source_paths,
                trace={"adapter": stage.transform_adapter, "output": output.name},
            )
        ]
    return outputs


def execute_stage_adapter(
    stage: StageDefinition,
    config: ProcessorConfig,
    items: list[InputItem],
    client: Any,
) -> dict[str, list[ArtifactEnvelope]]:
    del config
    adapter = stage.transform_adapter
    if adapter == "llm_map":
        return execute_generic_llm_map(stage, items, client)
    if adapter == "llm_reduce":
        return execute_generic_llm_reduce(stage, items, client)
    if adapter == "deterministic_map":
        return execute_deterministic_map(stage, items)
    if adapter == "deterministic_reduce":
        return execute_deterministic_reduce(stage, items)
    if adapter == "noop":
        return {output.name: [] for output in stage.outputs}
    raise ValueError(f"Unsupported stage adapter {adapter!r} for stage {stage.name}")
