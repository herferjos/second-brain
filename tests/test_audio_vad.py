"""Unit tests for audio VAD segmenter."""

from __future__ import annotations

import pytest

pytest.importorskip("sounddevice")
from exocort.capture.audio.models import AudioConfig
from exocort.capture.audio.vad import VadSegmenter


pytestmark = [pytest.mark.unit, pytest.mark.stt]


def test_vad_segmenter_rejects_invalid_sample_rate() -> None:
    config = AudioConfig(
        source="mic",
        sample_rate=44100,
        frame_ms=20,
        vad_mode=2,
        start_rms=150,
        continue_rms=100,
        start_trigger_ms=120,
        start_window_ms=400,
        end_silence_ms=700,
        pre_roll_ms=300,
        min_segment_ms=500,
        max_segment_ms=30_000,
        input_device=None,
    )
    with pytest.raises(ValueError, match="sample_rate"):
        VadSegmenter(config)


def test_vad_segmenter_rejects_invalid_frame_ms() -> None:
    config = AudioConfig(
        source="mic",
        sample_rate=16000,
        frame_ms=15,
        vad_mode=2,
        start_rms=150,
        continue_rms=100,
        start_trigger_ms=120,
        start_window_ms=400,
        end_silence_ms=700,
        pre_roll_ms=300,
        min_segment_ms=500,
        max_segment_ms=30_000,
        input_device=None,
    )
    with pytest.raises(ValueError, match="frame_ms"):
        VadSegmenter(config)


def test_vad_segmenter_feed_empty_returns_empty() -> None:
    config = AudioConfig(
        source="mic",
        sample_rate=16000,
        frame_ms=20,
        vad_mode=2,
        start_rms=150,
        continue_rms=100,
        start_trigger_ms=120,
        start_window_ms=400,
        end_silence_ms=700,
        pre_roll_ms=300,
        min_segment_ms=500,
        max_segment_ms=30_000,
        input_device=None,
    )
    seg = VadSegmenter(config)
    out = seg.feed(b"")
    assert out == []


def test_vad_segmenter_flush_when_not_recording_returns_none() -> None:
    config = AudioConfig(
        source="mic",
        sample_rate=16000,
        frame_ms=20,
        vad_mode=2,
        start_rms=150,
        continue_rms=100,
        start_trigger_ms=120,
        start_window_ms=400,
        end_silence_ms=700,
        pre_roll_ms=300,
        min_segment_ms=500,
        max_segment_ms=30_000,
        input_device=None,
    )
    seg = VadSegmenter(config)
    assert seg.flush() is None
