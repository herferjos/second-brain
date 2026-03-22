from __future__ import annotations

import logging
import wave
from pathlib import Path
from threading import Lock
from uuid import uuid4

import requests

from .device import remove_wav_and_meta, wav_rms
from .models import AudioSegment, Settings


class SpoolUploader:
    def __init__(self, settings_obj: Settings):
        self.settings = settings_obj
        self.settings.spool_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("audio_capturer.uploader")
        self._lock = Lock()

    def save_segment(
        self,
        segment: AudioSegment,
    ) -> Path:
        filename = f"{uuid4().hex}.wav"
        path = self.settings.spool_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(segment.sample_rate)
            wav_file.writeframes(segment.pcm_bytes)
        return path

    def flush_pending(self, max_files: int) -> None:
        with self._lock:
            files = sorted(self.settings.spool_dir.glob("*.wav"))[: max(1, max_files)]
            for path in files:
                if not self._upload(path):
                    break

    def _upload(self, wav_path: Path) -> bool:
        rms = wav_rms(wav_path)
        if rms < self.settings.min_rms:
            self.logger.info(
                "Discarding silent segment before upload | file=%s | min_rms=%d",
                wav_path.name,
                self.settings.min_rms,
            )
            return remove_wav_and_meta(wav_path, self.logger)

        try:
            with wav_path.open("rb") as f:
                files = {"file": (wav_path.name, f, "audio/wav")}
                response = requests.post(
                    self.settings.api_audio_url,
                    files=files,
                    timeout=self.settings.request_timeout_s,
                )
        except Exception:
            self.logger.exception("Upload failed | file=%s", wav_path.name)
            return False

        if response.status_code >= 300:
            self.logger.error(
                "Upload rejected | file=%s | status=%d | body=%s",
                wav_path.name,
                response.status_code,
                response.text[:300],
            )
            return False

        if not remove_wav_and_meta(wav_path, self.logger):
            return False

        self.logger.info("Uploaded segment | file=%s", wav_path.name)
        return True
