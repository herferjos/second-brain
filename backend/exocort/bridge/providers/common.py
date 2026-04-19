from __future__ import annotations

import json
from typing import Any

from ..models.ocr import OcrPage, OcrResult
from ..models.response import ResponseResult, ToolCall
from ..utils.messages import collect_tool_calls, text_from_content


def content_as_text_blocks(content: object) -> list[dict[str, Any]]:
    if isinstance(content, str) and content.strip():
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return []
    blocks: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            blocks.append({"type": "text", "text": text})
    return blocks


def normalize_function_arguments(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = json.loads(value or "{}")
    elif isinstance(value, dict):
        parsed = value
    else:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def compact_strings(values: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in values.items() if value != ""}


def float_to_str(value: float | None) -> str:
    if value is None:
        return ""
    return json.dumps(value)


def bearer_json_headers(api_key: str, extra_headers: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", **extra_headers}


def api_key_json_headers(header_name: str, api_key: str, extra_headers: dict[str, str]) -> dict[str, str]:
    return {header_name: api_key, "Content-Type": "application/json", **extra_headers}


def require_payload(payload: dict[str, Any] | None, label: str) -> dict[str, Any]:
    if payload is None:
        raise ValueError(f"{label} endpoint did not return JSON.")
    return payload


def response_from_chat_completion(payload_json: dict[str, Any]) -> ResponseResult:
    choices = payload_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("response payload must include choices.")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ValueError("response choice must be an object.")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("response choice must include a message object.")
    tool_calls = tuple(parse_tool_call(item) for item in collect_tool_calls(message))
    return ResponseResult(
        message=message,
        text=text_from_content(message.get("content")),
        tool_calls=tool_calls,
        raw=payload_json,
    )


def parse_tool_call(tool_call: dict[str, Any]) -> ToolCall:
    function = tool_call.get("function")
    if not isinstance(function, dict):
        raise ValueError("tool call must include function details.")
    raw_arguments = function.get("arguments", "{}")
    if isinstance(raw_arguments, str):
        arguments = json.loads(raw_arguments or "{}")
    elif isinstance(raw_arguments, dict):
        arguments = raw_arguments
    else:
        raise ValueError("tool arguments must be a JSON object.")
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must decode to an object.")
    return ToolCall(
        id=str(tool_call.get("id")) if tool_call.get("id") is not None else None,
        name=str(function.get("name", "")).strip(),
        arguments=arguments,
    )


def ensure_text(text: str, label: str) -> str:
    value = text.strip()
    if not value:
        raise ValueError(f"{label} is empty.")
    return value


def single_page_ocr_result(text: str, raw: dict[str, Any], label: str = "OCR page markdown") -> OcrResult:
    value = ensure_text(text, label)
    return OcrResult(text=value, pages=(OcrPage(index=0, text=value),), raw=raw)
