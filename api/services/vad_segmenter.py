import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional


logger = logging.getLogger("second_brain.vad")


@dataclass
class VADSegment:
    pcm_bytes: bytes
    duration_ms: int
    reason: str


class VADSegmenter:
    """
    Streaming VAD state machine:
    - Starts a segment when enough voiced frames are detected in a short window.
    - Ends a segment when sustained silence is detected.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 20,
        vad_mode: int = 2,
        start_trigger_ms: int = 240,
        start_window_ms: int = 400,
        end_silence_ms: int = 900,
        pre_roll_ms: int = 300,
        min_segment_ms: int = 1000,
        max_segment_ms: int = 30000,
    ):
        if sample_rate not in {8000, 16000, 32000, 48000}:
            raise ValueError("VAD sample_rate must be one of 8000, 16000, 32000, 48000")
        if frame_ms not in {10, 20, 30}:
            raise ValueError("VAD frame_ms must be one of 10, 20, 30")

        try:
            import webrtcvad
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency 'webrtcvad'. Install requirements for auto-listening."
            ) from exc

        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_bytes = int(sample_rate * frame_ms / 1000) * 2
        self.start_trigger_frames = max(1, int(start_trigger_ms / frame_ms))
        self.start_window_frames = max(
            self.start_trigger_frames, int(start_window_ms / frame_ms)
        )
        self.end_silence_frames = max(1, int(end_silence_ms / frame_ms))
        self.pre_roll_frames = max(1, int(pre_roll_ms / frame_ms))
        self.min_segment_frames = max(1, int(min_segment_ms / frame_ms))
        self.max_segment_frames = max(self.min_segment_frames, int(max_segment_ms / frame_ms))

        self._vad = webrtcvad.Vad(max(0, min(3, vad_mode)))
        self._buffer = b""
        self._in_speech = False
        self._current_frames: list[bytes] = []
        self._pre_roll = deque(maxlen=self.pre_roll_frames)
        self._recent_voicing = deque(maxlen=self.start_window_frames)
        self._silence_run = 0

    def process_pcm_chunk(self, pcm_chunk: bytes) -> list[VADSegment]:
        segments = []
        if not pcm_chunk:
            return segments

        self._buffer += pcm_chunk
        while len(self._buffer) >= self.frame_bytes:
            frame = self._buffer[: self.frame_bytes]
            self._buffer = self._buffer[self.frame_bytes :]
            segment = self._process_frame(frame)
            if segment is not None:
                segments.append(segment)
        return segments

    def flush(self) -> Optional[VADSegment]:
        if not self._in_speech:
            return None
        frames = self._current_frames
        if self._silence_run > 0 and self._silence_run < len(frames):
            frames = frames[: -self._silence_run]
        return self._finalize(frames, reason="shutdown")

    def _process_frame(self, frame: bytes) -> Optional[VADSegment]:
        is_speech = self._vad.is_speech(frame, self.sample_rate)
        self._pre_roll.append(frame)

        if not self._in_speech:
            self._recent_voicing.append(is_speech)
            voiced = sum(1 for flag in self._recent_voicing if flag)
            if voiced >= self.start_trigger_frames:
                self._in_speech = True
                self._silence_run = 0
                self._current_frames = list(self._pre_roll)
                self._recent_voicing.clear()
            return None

        self._current_frames.append(frame)

        if is_speech:
            self._silence_run = 0
        else:
            self._silence_run += 1

        if len(self._current_frames) >= self.max_segment_frames:
            return self._finalize(self._current_frames, reason="max_duration")

        if self._silence_run >= self.end_silence_frames:
            frames = self._current_frames
            if self._silence_run > 0 and self._silence_run < len(frames):
                frames = frames[: -self._silence_run]
            return self._finalize(frames, reason="silence")

        return None

    def _finalize(self, frames: list[bytes], reason: str) -> Optional[VADSegment]:
        segment = None
        frame_count = len(frames)
        if frame_count >= self.min_segment_frames:
            pcm_bytes = b"".join(frames)
            duration_ms = frame_count * self.frame_ms
            segment = VADSegment(
                pcm_bytes=pcm_bytes,
                duration_ms=duration_ms,
                reason=reason,
            )
            logger.info(
                "VAD segment finalized | duration_ms=%d | reason=%s",
                duration_ms,
                reason,
            )
        else:
            logger.debug(
                "VAD segment discarded (too short) | frames=%d | reason=%s",
                frame_count,
                reason,
            )

        self._in_speech = False
        self._current_frames = []
        self._silence_run = 0
        self._recent_voicing.clear()
        return segment
