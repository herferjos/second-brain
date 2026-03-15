"""Unit tests for collector forward (forward_upload)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("requests")
from exocort.collector.config import EndpointConfig
from exocort.collector.forward import forward_upload


pytestmark = pytest.mark.unit


@patch("exocort.collector.forward.requests.post")
def test_forward_upload_success(mock_post: MagicMock) -> None:
    mock_post.return_value.status_code = 200
    mock_post.return_value.text = '{"text": "hello"}'

    ep = EndpointConfig(url="http://localhost:9092/transcribe", timeout=10.0)
    ok, status, body = forward_upload(
        ep, b"wav-data", "x.wav", "audio/wav", {"segment_id": "s1"}
    )
    assert ok is True
    assert status == 200
    assert "hello" in body
    mock_post.assert_called_once()
    call_kw = mock_post.call_args[1]
    assert call_kw["timeout"] == 10.0
    assert call_kw["files"]["file"][0] == "x.wav"
    assert call_kw["data"] == {"segment_id": "s1"}


@patch("exocort.collector.forward.requests.post")
def test_forward_upload_rejected(mock_post: MagicMock) -> None:
    mock_post.return_value.status_code = 400
    mock_post.return_value.text = "Bad request"

    ep = EndpointConfig(url="http://localhost:9092/transcribe")
    ok, status, body = forward_upload(ep, b"", "x.wav", "audio/wav", {})
    assert ok is False
    assert status == 400
    assert body == "Bad request"


@patch("exocort.collector.forward.requests.post")
def test_forward_upload_no_form_when_forward_form_false(mock_post: MagicMock) -> None:
    mock_post.return_value.status_code = 200
    mock_post.return_value.text = ""

    ep = EndpointConfig(url="http://x/y", forward_form=False)
    forward_upload(ep, b"", "f.wav", "audio/wav", {"a": "b"})
    call_kw = mock_post.call_args[1]
    assert call_kw["data"] == {}
