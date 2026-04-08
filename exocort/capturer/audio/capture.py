from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import io
import time
import wave
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from .config import AudioCaptureConfig
from .vad import SimpleVAD


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
    chunks: list[np.ndarray] = field(default_factory=list)
    frames: int = 0
    recording: bool = False

    def push(self, chunk: np.ndarray, speech_detected: bool) -> np.ndarray | None:
        if speech_detected:
            self.recording = True
            self.chunks.append(chunk.copy())
            self.frames += int(chunk.shape[0])
            if self.frames >= self.max_frames:
                return self._finish()
            return None

        if not self.recording:
            return None

        return self._finish()

    def _finish(self) -> np.ndarray:
        segment = np.concatenate(self.chunks, axis=0)
        self.chunks.clear()
        self.frames = 0
        self.recording = False
        return segment


def _capture_vad_segment(
    config: AudioCaptureConfig,
    vad: SimpleVAD,
) -> tuple[np.ndarray, float]:
    window_frames = max(1, vad.window_samples)
    max_segment_frames = max(window_frames, int(config.chunk_seconds * config.sample_rate))
    collector = _SegmentCollector(max_frames=max_segment_frames)
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
    vad = SimpleVAD(config.vad, config.sample_rate) if config.vad.enabled else None

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
