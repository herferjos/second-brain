import json
import logging
import os
import queue
import wave
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Optional
from uuid import uuid4


logger = logging.getLogger("second_brain.audio_queue")


@dataclass
class AudioQueueItem:
    item_id: str
    wav_path: str
    metadata_path: str
    metadata: dict


class PersistentAudioQueue:
    """
    Queue backed by a spool directory so pending audio survives process restarts.
    """

    def __init__(self, spool_dir: str, max_size: int = 200):
        self.spool_dir = (
            spool_dir if os.path.isabs(spool_dir) else os.path.abspath(spool_dir)
        )
        self._queue: queue.Queue[str] = queue.Queue(maxsize=max(1, max_size))
        self._lock = Lock()

    def start(self):
        os.makedirs(self.spool_dir, exist_ok=True)
        self._rehydrate_pending()

    def enqueue_pcm16(
        self,
        pcm_bytes: bytes,
        sample_rate: int,
        metadata: Optional[dict] = None,
    ) -> str:
        if not pcm_bytes:
            raise ValueError("Cannot enqueue empty audio payload")
        if sample_rate <= 0:
            raise ValueError("Invalid sample_rate")

        item_id = uuid4().hex
        wav_path = self._wav_path(item_id)
        meta_path = self._meta_path(item_id)
        duration_ms = int(len(pcm_bytes) / (sample_rate * 2) * 1000)

        with wave.open(wav_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)

        entry = {
            "item_id": item_id,
            "created_at": datetime.now().isoformat(),
            "status": "queued",
            "attempts": 0,
            "sample_rate": sample_rate,
            "duration_ms": duration_ms,
            "metadata": metadata or {},
        }
        self._write_json(meta_path, entry)

        try:
            self._queue.put_nowait(item_id)
            logger.info(
                "Audio segment enqueued | item_id=%s | duration_ms=%d",
                item_id,
                duration_ms,
            )
            return item_id
        except queue.Full:
            self.mark_error(item_id, "queue_full", keep_audio=True)
            raise RuntimeError("Audio queue is full")

    def dequeue(self, timeout: float = 1.0) -> Optional[AudioQueueItem]:
        try:
            item_id = self._queue.get(timeout=max(0.0, timeout))
        except queue.Empty:
            return None

        metadata_path = self._meta_path(item_id)
        metadata = self._read_json(metadata_path)
        if metadata is None:
            logger.warning("Queue item metadata missing | item_id=%s", item_id)
            self._queue.task_done()
            return None

        metadata["status"] = "processing"
        metadata["attempts"] = int(metadata.get("attempts", 0)) + 1
        metadata["updated_at"] = datetime.now().isoformat()
        self._write_json(metadata_path, metadata)

        return AudioQueueItem(
            item_id=item_id,
            wav_path=self._wav_path(item_id),
            metadata_path=metadata_path,
            metadata=metadata,
        )

    def acknowledge(self):
        self._queue.task_done()

    def mark_done(self, item_id: str, keep_metadata: bool = False):
        metadata_path = self._meta_path(item_id)
        metadata = self._read_json(metadata_path)
        if metadata:
            metadata["status"] = "done"
            metadata["updated_at"] = datetime.now().isoformat()
            self._write_json(metadata_path, metadata)

        self._remove_if_exists(self._wav_path(item_id))
        if not keep_metadata:
            self._remove_if_exists(metadata_path)
        logger.info("Queue item completed | item_id=%s", item_id)

    def mark_error(self, item_id: str, error: str, keep_audio: bool = True):
        metadata_path = self._meta_path(item_id)
        metadata = self._read_json(metadata_path) or {"item_id": item_id}
        metadata["status"] = "error"
        metadata["error"] = str(error)
        metadata["updated_at"] = datetime.now().isoformat()
        self._write_json(metadata_path, metadata)

        if not keep_audio:
            self._remove_if_exists(self._wav_path(item_id))
        logger.error("Queue item failed | item_id=%s | error=%s", item_id, error)

    def requeue(self, item_id: str):
        metadata_path = self._meta_path(item_id)
        metadata = self._read_json(metadata_path)
        if not metadata:
            return
        metadata["status"] = "queued"
        metadata["updated_at"] = datetime.now().isoformat()
        self._write_json(metadata_path, metadata)
        try:
            self._queue.put_nowait(item_id)
            logger.info("Queue item requeued | item_id=%s", item_id)
        except queue.Full:
            self.mark_error(item_id, "queue_full_on_requeue", keep_audio=True)

    def _rehydrate_pending(self):
        meta_files = sorted(
            f
            for f in os.listdir(self.spool_dir)
            if f.endswith(".json") and os.path.isfile(os.path.join(self.spool_dir, f))
        )
        restored = 0
        for filename in meta_files:
            item_id = filename[:-5]
            metadata = self._read_json(os.path.join(self.spool_dir, filename))
            if not metadata:
                continue
            wav_path = self._wav_path(item_id)
            if not os.path.exists(wav_path):
                self.mark_error(item_id, "missing_audio_file", keep_audio=False)
                continue
            if metadata.get("status") not in {"queued", "processing"}:
                continue
            metadata["status"] = "queued"
            metadata["updated_at"] = datetime.now().isoformat()
            self._write_json(os.path.join(self.spool_dir, filename), metadata)
            try:
                self._queue.put_nowait(item_id)
                restored += 1
            except queue.Full:
                logger.warning("Queue full while rehydrating pending items")
                break

        if restored:
            logger.info("Pending audio restored from spool | count=%d", restored)

    def _wav_path(self, item_id: str) -> str:
        return os.path.join(self.spool_dir, f"{item_id}.wav")

    def _meta_path(self, item_id: str) -> str:
        return os.path.join(self.spool_dir, f"{item_id}.json")

    def _write_json(self, path: str, data: dict):
        with self._lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

    def _read_json(self, path: str) -> Optional[dict]:
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.exception("Failed to read metadata JSON | path=%s", path)
            return None

    @staticmethod
    def _remove_if_exists(path: str):
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                logger.exception("Failed to remove file | path=%s", path)
