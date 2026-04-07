from __future__ import annotations

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

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(config.channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(config.sample_rate)
        wav_file.writeframes(recording.tobytes())

    return recording, buffer.getvalue()


def audio_loop(
    config: AudioCaptureConfig,
    handler: Callable[[bytes], None] | None = None,
) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = config.output_dir
    vad = SimpleVAD(config.vad, config.sample_rate) if config.vad.enabled else None

    while True:
        started_at = time.monotonic()
        recording, audio_bytes = capture_audio_chunk(config)
        elapsed = time.monotonic() - started_at
        speech_detected = True
        if vad is not None:
            speech_detected = vad.is_speech(recording)
        if not speech_detected:
            print(
                f"[audio] skipping {len(audio_bytes)} bytes ({elapsed:.1f}s); "
                f"VAD speech ratio {vad.last_ratio:.2%}"
            )
            continue
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
        file_path = output_dir / f"{timestamp}.wav"
        file_path.write_bytes(audio_bytes)
        vad_suffix = f" (VAD ratio {vad.last_ratio:.2%})" if vad is not None else ""
        print(f"[audio] captured {len(audio_bytes)} bytes ({elapsed:.1f}s) → {file_path}{vad_suffix}")
        if handler is not None:
            handler(audio_bytes)
