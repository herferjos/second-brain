from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import io
import time
import wave
from collections import deque
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from .config import AudioCaptureConfig
from .vad import WebRTCVAD


def capture_audio_chunk(config: AudioCaptureConfig) -> tuple[np.ndarray, bytes]:
    frames = int(config.chunk_seconds * config.sample_rate)
    recording = sd.rec(
        frames,
        samplerate=config.sample_rate,
        channels=config.channels,
        dtype="int16",
    )
    sd.wait()
    return recording, _encode_wav(config, recording)


def _encode_wav(config: AudioCaptureConfig, recording: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(config.channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(config.sample_rate)
        wav_file.writeframes(recording.astype(np.int16, copy=False).tobytes())
    return buffer.getvalue()


@dataclass(slots=True)
class _SegmentCollector:
    max_frames: int
    pre_roll_chunks: int
    min_speech_chunks: int
    min_silence_chunks: int
    pre_roll: deque[np.ndarray] = field(init=False)
    pending_speech: list[np.ndarray] = field(default_factory=list)
    chunks: list[np.ndarray] = field(default_factory=list)
    frames: int = 0
    recording: bool = False
    speech_chunks: int = 0
    silence_chunks: int = 0

    def __post_init__(self) -> None:
        self.pre_roll = deque(maxlen=self.pre_roll_chunks)

    def push(self, chunk: np.ndarray, speech_detected: bool) -> np.ndarray | None:
        chunk_copy = chunk.copy()

        if self.recording:
            self.chunks.append(chunk_copy)
            self.frames += int(chunk.shape[0])
            if speech_detected:
                self.speech_chunks += 1
                self.silence_chunks = 0
            else:
                self.silence_chunks += 1
            if self.frames >= self.max_frames or self.silence_chunks >= self.min_silence_chunks:
                return self._finish()
            return None

        if speech_detected:
            self.pending_speech.append(chunk_copy)
            self.speech_chunks += 1
            if self.speech_chunks >= self.min_speech_chunks:
                self.recording = True
                self.chunks = [*self.pre_roll, *self.pending_speech]
                self.frames = sum(int(part.shape[0]) for part in self.chunks)
                self.pending_speech.clear()
                self.silence_chunks = 0
                if self.frames >= self.max_frames:
                    return self._finish()
            return None

        self.pre_roll.append(chunk_copy)
        self.pending_speech.clear()
        self.speech_chunks = 0
        return None

    def _finish(self) -> np.ndarray:
        segment = np.concatenate(self.chunks, axis=0)
        self.pre_roll.clear()
        self.pending_speech.clear()
        self.chunks.clear()
        self.frames = 0
        self.recording = False
        self.speech_chunks = 0
        self.silence_chunks = 0
        return segment


def _capture_vad_segment(
    config: AudioCaptureConfig,
    vad: WebRTCVAD,
) -> tuple[np.ndarray, float]:
    window_frames = max(1, vad.frame_samples)
    max_segment_frames = max(window_frames, int(config.chunk_seconds * config.sample_rate))
    collector = _SegmentCollector(
        max_frames=max_segment_frames,
        pre_roll_chunks=max(0, int(round(config.vad.pre_roll_seconds * config.sample_rate / window_frames))),
        min_speech_chunks=max(
            1,
            int(round(config.vad.min_speech_seconds * config.sample_rate / window_frames)),
        ),
        min_silence_chunks=max(
            1,
            int(round(config.vad.min_silence_seconds * config.sample_rate / window_frames)),
        ),
    )
    started_at = time.monotonic()

    with sd.InputStream(
        samplerate=config.sample_rate,
        channels=config.channels,
        dtype="int16",
        blocksize=window_frames,
    ) as stream:
        while True:
            chunk, _ = stream.read(window_frames)
            speech_detected = vad.is_speech(chunk)
            segment = collector.push(chunk, speech_detected)
            if segment is None:
                continue
            return segment, time.monotonic() - started_at


def audio_loop(
    config: AudioCaptureConfig,
    handler: Callable[[bytes], None] | None = None,
) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = config.output_dir
    vad = WebRTCVAD(config.vad, config.sample_rate) if config.vad.enabled else None

    while True:
        if vad is None:
            started_at = time.monotonic()
            recording, audio_bytes = capture_audio_chunk(config)
            elapsed = time.monotonic() - started_at
        else:
            recording, elapsed = _capture_vad_segment(config, vad)
            audio_bytes = _encode_wav(config, recording)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
        file_path = output_dir / f"{timestamp}.wav"
        file_path.write_bytes(audio_bytes)
        vad_suffix = f" (VAD ratio {vad.last_ratio:.2%})" if vad is not None else ""
        print(f"[audio] captured {len(audio_bytes)} bytes ({elapsed:.1f}s) → {file_path}{vad_suffix}")
        if handler is not None:
            handler(audio_bytes)
