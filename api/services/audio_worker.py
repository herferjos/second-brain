import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from threading import Event, Thread
from typing import Optional

from api.config import settings
from api.services.audio_queue import AudioQueueItem, PersistentAudioQueue
from api.services.brain_manager import save_to_brain
from api.services.life_log import append_entry
from api.services.llm import process_session_with_llm
from api.services.transcriber import transcriber


logger = logging.getLogger("second_brain.audio_worker")


@dataclass
class _PendingSegment:
    item: AudioQueueItem
    text: str
    created_at: datetime


class AudioProcessingWorker:
    """
    Dequeues VAD segments, transcribes them, and flushes grouped text to the LLM.
    """

    def __init__(self, audio_queue: PersistentAudioQueue):
        self.audio_queue = audio_queue
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._batch: list[_PendingSegment] = []
        self._batch_started_mono: Optional[float] = None
        self._batch_last_mono: Optional[float] = None
        self._batch_last_created_at: Optional[datetime] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._run, name="audio-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _run(self):
        logger.info(
            "Audio worker started | poll_s=%.2f | max_wait_s=%.2f | min_words=%d",
            settings.AUDIO_WORKER_POLL_SECONDS,
            settings.AUDIO_FLUSH_MAX_WAIT_SECONDS,
            settings.AUDIO_FLUSH_MIN_WORDS,
        )
        while not self._stop_event.is_set():
            item = self.audio_queue.dequeue(timeout=settings.AUDIO_WORKER_POLL_SECONDS)
            if item is None:
                self._flush_if_stale()
                continue

            try:
                self._handle_item(item)
            except Exception:
                logger.exception("Audio worker failed processing item | item_id=%s", item.item_id)
                self._retry_or_fail(item, "worker_exception")
            finally:
                self.audio_queue.acknowledge()

        self._flush_batch(reason="shutdown")
        logger.info("Audio worker stopped")

    def _handle_item(self, item: AudioQueueItem):
        attempts = int(item.metadata.get("attempts", 1))
        if attempts > settings.AUDIO_MAX_RETRIES:
            logger.error(
                "Audio item exceeded retries | item_id=%s | attempts=%d",
                item.item_id,
                attempts,
            )
            self.audio_queue.mark_error(item.item_id, "max_retries_exceeded", keep_audio=True)
            return

        text = transcriber.transcribe(item.wav_path, job_id=item.item_id)
        if not text.strip():
            logger.error("Empty transcription from queued item | item_id=%s", item.item_id)
            self._retry_or_fail(item, "empty_transcription")
            return

        created_at = _parse_iso_datetime(item.metadata.get("created_at"))
        if (
            self._batch
            and self._batch_last_created_at is not None
            and (created_at - self._batch_last_created_at).total_seconds()
            > settings.AUDIO_FLUSH_SILENCE_GAP_SECONDS
        ):
            self._flush_batch(reason="silence_gap")

        now_mono = time.monotonic()
        if self._batch_started_mono is None:
            self._batch_started_mono = now_mono
        self._batch_last_mono = now_mono
        self._batch_last_created_at = created_at
        self._batch.append(_PendingSegment(item=item, text=text.strip(), created_at=created_at))

        words = self._word_count()
        elapsed = now_mono - self._batch_started_mono
        if len(self._batch) >= settings.AUDIO_MAX_BATCH_SEGMENTS:
            self._flush_batch(reason="max_batch_segments")
        elif words >= settings.AUDIO_FLUSH_MIN_WORDS:
            self._flush_batch(reason="min_words_reached")
        elif elapsed >= settings.AUDIO_FLUSH_MAX_WAIT_SECONDS:
            self._flush_batch(reason="max_wait_reached")

    def _flush_if_stale(self):
        if not self._batch or self._batch_last_mono is None:
            return
        idle_for = time.monotonic() - self._batch_last_mono
        if idle_for >= settings.AUDIO_FLUSH_MAX_WAIT_SECONDS:
            self._flush_batch(reason="idle_timeout")

    def _flush_batch(self, reason: str):
        if not self._batch:
            return

        batch = self._batch
        text = "\n\n".join(segment.text for segment in batch if segment.text)
        item_ids = [segment.item.item_id for segment in batch]
        logger.info(
            "Flushing audio batch | reason=%s | segments=%d | words=%d",
            reason,
            len(batch),
            len(text.split()),
        )

        if not text.strip():
            for segment in batch:
                self.audio_queue.mark_done(segment.item.item_id)
            self._reset_batch()
            return

        try:
            result = process_session_with_llm({"transcription": text}, job_id=item_ids[0][:8])
            if not result or "content" not in result:
                raise RuntimeError("invalid_llm_output")

            path = save_to_brain(result)
            append_entry(
                entry_type="audio_auto",
                summary=result.get("filename", "untitled"),
                metadata={
                    "segments_count": len(batch),
                    "source_files": [os.path.basename(segment.item.wav_path) for segment in batch],
                    "transcription_length": len(text),
                    "category": result.get("category"),
                    "saved_to": path,
                    "flush_reason": reason,
                },
            )
            for segment in batch:
                self.audio_queue.mark_done(segment.item.item_id)
            logger.info("Audio batch archived | segments=%d | path=%s", len(batch), path)
        except Exception:
            logger.exception("Failed to flush audio batch | reason=%s", reason)
            for segment in batch:
                self._retry_or_fail(segment.item, "llm_flush_failed")
        finally:
            self._reset_batch()

    def _retry_or_fail(self, item: AudioQueueItem, error: str):
        attempts = int(item.metadata.get("attempts", 1))
        if attempts >= settings.AUDIO_MAX_RETRIES:
            self.audio_queue.mark_error(item.item_id, error, keep_audio=True)
        else:
            self.audio_queue.requeue(item.item_id)

    def _reset_batch(self):
        self._batch = []
        self._batch_started_mono = None
        self._batch_last_mono = None
        self._batch_last_created_at = None

    def _word_count(self) -> int:
        return sum(len(segment.text.split()) for segment in self._batch if segment.text)


def _parse_iso_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now()
