from __future__ import annotations

import audioop
from collections import deque

import webrtcvad

from .models import AudioConfig, AudioSegment


class VadSegmenter:
    def __init__(self, config: AudioConfig) -> None:
        if config.sample_rate not in {8000, 16000, 32000, 48000}:
            raise ValueError("sample_rate must be 8000, 16000, 32000 or 48000")
        if config.frame_ms not in {10, 20, 30}:
            raise ValueError("frame_ms must be 10, 20 or 30")

        self.config = config
        self.frame_bytes = int(config.sample_rate * config.frame_ms / 1000) * 2
        self.start_trigger_frames = max(
            1, int(config.start_trigger_ms / config.frame_ms)
        )
        self.start_window_frames = max(1, int(config.start_window_ms / config.frame_ms))
        self.end_silence_frames = max(1, int(config.end_silence_ms / config.frame_ms))
        self.pre_roll_frames = max(1, int(config.pre_roll_ms / config.frame_ms))
        self.min_segment_frames = max(1, int(config.min_segment_ms / config.frame_ms))
        self.max_segment_frames = max(1, int(config.max_segment_ms / config.frame_ms))

        self._vad = webrtcvad.Vad(max(0, min(3, config.vad_mode)))
        self._buffer = b""
        self._pre_roll: deque[bytes] = deque(maxlen=self.pre_roll_frames)
        self._recent_flags: deque[bool] = deque(maxlen=self.start_window_frames)
        self._frames: list[bytes] = []
        self._silence_frames = 0
        self._recording = False

    def feed(self, chunk: bytes) -> list[AudioSegment]:
        segments: list[AudioSegment] = []
        if not chunk:
            return segments

        self._buffer += chunk
        while len(self._buffer) >= self.frame_bytes:
            frame = self._buffer[: self.frame_bytes]
            self._buffer = self._buffer[self.frame_bytes :]
            segment = self._feed_frame(frame)
            if segment is not None:
                segments.append(segment)
        return segments

    def flush(self) -> AudioSegment | None:
        if not self._recording:
            return None
        return self._finalize(self._frames, "stop")

    def _feed_frame(self, frame: bytes) -> AudioSegment | None:
        rms = int(audioop.rms(frame, 2)) if frame else 0
        is_speech = self._vad.is_speech(frame, self.config.sample_rate)
        start_active = is_speech and rms >= self.config.start_rms
        continue_active = is_speech and rms >= self.config.continue_rms
        self._pre_roll.append(frame)

        if not self._recording:
            self._recent_flags.append(start_active)
            if (
                sum(1 for flag in self._recent_flags if flag)
                >= self.start_trigger_frames
            ):
                self._recording = True
                self._silence_frames = 0
                self._frames = list(self._pre_roll)
                self._recent_flags.clear()
            return None

        self._frames.append(frame)
        if continue_active:
            self._silence_frames = 0
        else:
            self._silence_frames += 1

        if len(self._frames) >= self.max_segment_frames:
            return self._finalize(self._frames, "max_segment")

        if self._silence_frames >= self.end_silence_frames:
            frames = self._frames[: -self._silence_frames] or self._frames
            return self._finalize(frames, "silence")
        return None

    def _finalize(self, frames: list[bytes], ended_by: str) -> AudioSegment | None:
        frame_count = len(frames)
        segment = None
        if frame_count >= self.min_segment_frames:
            pcm_bytes = b"".join(frames)
            rms = int(audioop.rms(pcm_bytes, 2)) if pcm_bytes else 0
            if rms > 0:
                segment = AudioSegment(
                    source=self.config.source,
                    pcm_bytes=pcm_bytes,
                    sample_rate=self.config.sample_rate,
                    duration_ms=frame_count * self.config.frame_ms,
                    rms=rms,
                    ended_by=ended_by,
                )

        self._frames = []
        self._silence_frames = 0
        self._recording = False
        self._recent_flags.clear()
        return segment
