import json
import logging
import os
import time
import wave
import audioop
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import requests
import sounddevice as sd
import webrtcvad
from dotenv import load_dotenv


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


@dataclass
class Settings:
    api_audio_url: str
    sample_rate: int
    frame_ms: int
    vad_mode: int
    start_trigger_ms: int
    start_window_ms: int
    end_silence_ms: int
    pre_roll_ms: int
    min_segment_ms: int
    max_segment_ms: int
    input_device: str | None
    spool_dir: Path
    request_timeout_s: float
    max_upload_per_cycle: int
    min_rms: int

    @classmethod
    def from_env(cls) -> "Settings":
        input_device = (
            os.getenv("AUDIO_CAPTURE_INPUT_DEVICE")
            or os.getenv("AUDIO_BRIDGE_INPUT_DEVICE", "")
        ).strip() or None
        spool_dir_raw = (
            os.getenv("AUDIO_CAPTURE_SPOOL_DIR")
            or os.getenv("AUDIO_BRIDGE_SPOOL_DIR", "audio_capture/spool")
        )
        spool_dir = Path(spool_dir_raw).expanduser()
        api_audio_url = (
            os.getenv("AUDIO_CAPTURE_API_AUDIO_URL")
            or os.getenv("AUDIO_BRIDGE_API_AUDIO_URL", "http://127.0.0.1:8787/audio")
        )

        return cls(
            api_audio_url=api_audio_url,
            sample_rate=_env_int("AUDIO_CAPTURE_SAMPLE_RATE", 0) or _env_int("AUDIO_BRIDGE_SAMPLE_RATE", 16000),
            frame_ms=_env_int("AUDIO_CAPTURE_FRAME_MS", 0) or _env_int("AUDIO_BRIDGE_FRAME_MS", 20),
            vad_mode=_env_int("AUDIO_CAPTURE_VAD_MODE", 2) if os.getenv("AUDIO_CAPTURE_VAD_MODE") else (_env_int("AUDIO_BRIDGE_VAD_MODE", 2)),
            start_trigger_ms=_env_int("AUDIO_CAPTURE_START_TRIGGER_MS", 0) or _env_int("AUDIO_BRIDGE_START_TRIGGER_MS", 240),
            start_window_ms=_env_int("AUDIO_CAPTURE_START_WINDOW_MS", 0) or _env_int("AUDIO_BRIDGE_START_WINDOW_MS", 400),
            end_silence_ms=_env_int("AUDIO_CAPTURE_END_SILENCE_MS", 0) or _env_int("AUDIO_BRIDGE_END_SILENCE_MS", 900),
            pre_roll_ms=_env_int("AUDIO_CAPTURE_PRE_ROLL_MS", 0) or _env_int("AUDIO_BRIDGE_PRE_ROLL_MS", 300),
            min_segment_ms=_env_int("AUDIO_CAPTURE_MIN_SEGMENT_MS", 0) or _env_int("AUDIO_BRIDGE_MIN_SEGMENT_MS", 1000),
            max_segment_ms=_env_int("AUDIO_CAPTURE_MAX_SEGMENT_MS", 0) or _env_int("AUDIO_BRIDGE_MAX_SEGMENT_MS", 30000),
            input_device=input_device,
            spool_dir=spool_dir,
            request_timeout_s=_env_float("AUDIO_CAPTURE_REQUEST_TIMEOUT_S", 0) or _env_float("AUDIO_BRIDGE_REQUEST_TIMEOUT_S", 20.0),
            max_upload_per_cycle=_env_int("AUDIO_CAPTURE_MAX_UPLOAD_PER_CYCLE", 0) or _env_int("AUDIO_BRIDGE_MAX_UPLOAD_PER_CYCLE", 10),
            min_rms=_env_int("AUDIO_CAPTURE_MIN_RMS", 0) or _env_int("AUDIO_BRIDGE_MIN_RMS", 200),
        )


@dataclass
class VADSegment:
    pcm_bytes: bytes
    duration_ms: int
    reason: str


class VADSegmenter:
    def __init__(
        self,
        sample_rate: int,
        frame_ms: int,
        vad_mode: int,
        start_trigger_ms: int,
        start_window_ms: int,
        end_silence_ms: int,
        pre_roll_ms: int,
        min_segment_ms: int,
        max_segment_ms: int,
    ):
        if sample_rate not in {8000, 16000, 32000, 48000}:
            raise ValueError("sample_rate must be one of 8000,16000,32000,48000")
        if frame_ms not in {10, 20, 30}:
            raise ValueError("frame_ms must be one of 10,20,30")

        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_bytes = int(sample_rate * frame_ms / 1000) * 2
        self.start_trigger_frames = max(1, int(start_trigger_ms / frame_ms))
        self.start_window_frames = max(self.start_trigger_frames, int(start_window_ms / frame_ms))
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
        out = []
        if not pcm_chunk:
            return out
        self._buffer += pcm_chunk
        while len(self._buffer) >= self.frame_bytes:
            frame = self._buffer[: self.frame_bytes]
            self._buffer = self._buffer[self.frame_bytes :]
            segment = self._process_frame(frame)
            if segment is not None:
                out.append(segment)
        return out

    def flush(self) -> VADSegment | None:
        if not self._in_speech:
            return None
        frames = self._current_frames
        if self._silence_run > 0 and self._silence_run < len(frames):
            frames = frames[: -self._silence_run]
        return self._finalize(frames, "shutdown")

    def _process_frame(self, frame: bytes) -> VADSegment | None:
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
            return self._finalize(self._current_frames, "max_duration")

        if self._silence_run >= self.end_silence_frames:
            frames = self._current_frames
            if self._silence_run > 0 and self._silence_run < len(frames):
                frames = frames[: -self._silence_run]
            return self._finalize(frames, "silence")
        return None

    def _finalize(self, frames: list[bytes], reason: str) -> VADSegment | None:
        frame_count = len(frames)
        segment = None
        if frame_count >= self.min_segment_frames:
            duration_ms = frame_count * self.frame_ms
            segment = VADSegment(pcm_bytes=b"".join(frames), duration_ms=duration_ms, reason=reason)

        self._in_speech = False
        self._current_frames = []
        self._silence_run = 0
        self._recent_voicing.clear()
        return segment


class SpoolUploader:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.spool_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("audio_capture.uploader")

    def save_segment(
        self,
        pcm_bytes: bytes,
        sample_rate: int,
        duration_ms: int | None = None,
        vad_reason: str | None = None,
    ) -> Path:
        seg_id = uuid4().hex
        filename = f"{int(time.time() * 1000)}_{seg_id}.wav"
        path = self.settings.spool_dir / filename
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)
        meta_path = path.with_suffix(".wav.meta.json")
        if duration_ms is not None or vad_reason is not None:
            meta_path.write_text(
                json.dumps({"duration_ms": duration_ms, "vad_reason": vad_reason}),
                encoding="utf-8",
            )
        return path

    def flush_pending(self, max_files: int):
        files = sorted(self.settings.spool_dir.glob("*.wav"))[:max(1, max_files)]
        for path in files:
            if not self._upload(path):
                    break

    def _upload(self, wav_path: Path) -> bool:
        if _wav_rms(wav_path) < self.settings.min_rms:
            self.logger.info(
                "Discarding silent segment before upload | file=%s | min_rms=%d",
                wav_path.name,
                self.settings.min_rms,
            )
            try:
                wav_path.unlink()
                meta = wav_path.with_suffix(".wav.meta.json")
                if meta.exists():
                    meta.unlink()
            except OSError:
                self.logger.exception("Failed to remove silent file | file=%s", wav_path)
                return False
            return True

        meta_path = wav_path.with_suffix(".wav.meta.json")
        meta_data = {}
        if meta_path.exists():
            try:
                meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        segment_id = wav_path.stem
        duration_ms = meta_data.get("duration_ms")
        vad_reason = meta_data.get("vad_reason")
        rms = _wav_rms(wav_path)

        try:
            with wav_path.open("rb") as f:
                files = {"file": (wav_path.name, f, "audio/wav")}
                data = {
                    "segment_id": segment_id,
                    "sample_rate": str(self.settings.sample_rate),
                }
                if duration_ms is not None:
                    data["duration_ms"] = str(duration_ms)
                if vad_reason is not None:
                    data["vad_reason"] = str(vad_reason)
                if rms is not None:
                    data["rms"] = str(rms)
                response = requests.post(
                    self.settings.api_audio_url,
                    files=files,
                    data=data,
                    timeout=self.settings.request_timeout_s,
                )
        except Exception:
            self.logger.exception("Upload failed | file=%s", wav_path)
            return False

        if response.status_code >= 300:
            self.logger.error(
                "Upload rejected | file=%s | status=%d | body=%s",
                wav_path,
                response.status_code,
                response.text[:300],
            )
            return False

        try:
            wav_path.unlink()
            if meta_path.exists():
                meta_path.unlink()
        except OSError:
            self.logger.exception("Failed to remove uploaded file | file=%s", wav_path)
            return False

        self.logger.info("Uploaded segment | file=%s", wav_path.name)
        return True


def run():
    load_dotenv()
    settings = Settings.from_env()

    logging.basicConfig(
        level=os.getenv("AUDIO_CAPTURE_LOG_LEVEL") or os.getenv("AUDIO_BRIDGE_LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger = logging.getLogger("audio_capture")
    enabled_raw = os.getenv("AUDIO_CAPTURE_ENABLED") or os.getenv("AUDIO_BRIDGE_ENABLED", "")
    enabled = (enabled_raw or "").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        logger.info(
            "Audio capture disabled (set AUDIO_CAPTURE_ENABLED=1 to enable). "
            "Use the browser extension to send tab audio to the collector instead."
        )
        return
    logger.info("Starting audio capture | api_audio_url=%s", settings.api_audio_url)

    segmenter = VADSegmenter(
        sample_rate=settings.sample_rate,
        frame_ms=settings.frame_ms,
        vad_mode=settings.vad_mode,
        start_trigger_ms=settings.start_trigger_ms,
        start_window_ms=settings.start_window_ms,
        end_silence_ms=settings.end_silence_ms,
        pre_roll_ms=settings.pre_roll_ms,
        min_segment_ms=settings.min_segment_ms,
        max_segment_ms=settings.max_segment_ms,
    )
    uploader = SpoolUploader(settings)
    uploader.flush_pending(max_files=10_000)

    frame_samples = int(settings.sample_rate * settings.frame_ms / 1000)
    stream_kwargs = {
        "samplerate": settings.sample_rate,
        "channels": 1,
        "dtype": "int16",
        "blocksize": frame_samples,
    }
    if settings.input_device:
        stream_kwargs["device"] = settings.input_device

    logger.info(
        "Listening microphone | sample_rate=%d | frame_ms=%d | vad_mode=%d | min_rms=%d | device=%s",
        settings.sample_rate,
        settings.frame_ms,
        settings.vad_mode,
        settings.min_rms,
        settings.input_device or "default",
    )

    try:
        with sd.RawInputStream(**stream_kwargs) as stream:
            while True:
                data, overflowed = stream.read(frame_samples)
                if overflowed:
                    logger.warning("Audio input overflow detected")

                for segment in segmenter.process_pcm_chunk(bytes(data)):
                    if _pcm_rms(segment.pcm_bytes) < settings.min_rms:
                        logger.info(
                            "Segment dropped (silent) | duration_ms=%d | reason=%s | min_rms=%d",
                            segment.duration_ms,
                            segment.reason,
                            settings.min_rms,
                        )
                        continue
                    saved = uploader.save_segment(
                        segment.pcm_bytes,
                        settings.sample_rate,
                        duration_ms=segment.duration_ms,
                        vad_reason=segment.reason,
                    )
                    logger.info(
                        "Segment queued | file=%s | duration_ms=%d | reason=%s",
                        saved.name,
                        segment.duration_ms,
                        segment.reason,
                    )
                    uploader.flush_pending(max_files=settings.max_upload_per_cycle)
    except KeyboardInterrupt:
        logger.info("Stopping audio capture by user request")
    except Exception:
        logger.exception("Audio bridge failed")
    finally:
        tail = segmenter.flush()
        if tail and _pcm_rms(tail.pcm_bytes) >= settings.min_rms:
            uploader.save_segment(
                tail.pcm_bytes,
                settings.sample_rate,
                duration_ms=tail.duration_ms,
                vad_reason=tail.reason,
            )
        uploader.flush_pending(max_files=10_000)
        logger.info("Audio capture stopped")


def _pcm_rms(pcm_bytes: bytes) -> int:
    if not pcm_bytes:
        return 0
    return int(audioop.rms(pcm_bytes, 2))


def _wav_rms(path: Path) -> int:
    try:
        with wave.open(str(path), "rb") as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
        return _pcm_rms(frames)
    except Exception:
        return 0


if __name__ == "__main__":
    run()
