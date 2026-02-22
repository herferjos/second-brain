import logging
from threading import Event, Thread
from typing import Optional

from api.config import settings
from api.services.audio_queue import PersistentAudioQueue
from api.services.vad_segmenter import VADSegment, VADSegmenter


logger = logging.getLogger("second_brain.audio_listener")


class AudioListener:
    """
    Continuous microphone listener that segments speech with VAD and enqueues it.
    """

    def __init__(self, audio_queue: PersistentAudioQueue):
        self.audio_queue = audio_queue
        self._stop_event = Event()
        self._thread: Optional[Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._run, name="audio-listener", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _run(self):
        try:
            import sounddevice as sd
        except ImportError:
            logger.exception(
                "Audio auto-listening disabled: missing dependency 'sounddevice'"
            )
            return

        try:
            segmenter = VADSegmenter(
                sample_rate=settings.AUDIO_SAMPLE_RATE,
                frame_ms=settings.AUDIO_FRAME_MS,
                vad_mode=settings.AUDIO_VAD_MODE,
                start_trigger_ms=settings.AUDIO_VAD_START_TRIGGER_MS,
                start_window_ms=settings.AUDIO_VAD_START_WINDOW_MS,
                end_silence_ms=settings.AUDIO_VAD_END_SILENCE_MS,
                pre_roll_ms=settings.AUDIO_VAD_PRE_ROLL_MS,
                min_segment_ms=settings.AUDIO_VAD_MIN_SEGMENT_MS,
                max_segment_ms=settings.AUDIO_VAD_MAX_SEGMENT_MS,
            )
        except Exception:
            logger.exception("Audio auto-listening disabled: VAD initialization failed")
            return

        frame_samples = int(settings.AUDIO_SAMPLE_RATE * settings.AUDIO_FRAME_MS / 1000)
        channels = settings.AUDIO_CHANNELS
        if channels != 1:
            logger.warning(
                "AUDIO_CHANNELS=%d is not supported by VAD; forcing mono channel=1",
                channels,
            )
            channels = 1

        stream_kwargs = {
            "samplerate": settings.AUDIO_SAMPLE_RATE,
            "channels": channels,
            "dtype": "int16",
            "blocksize": frame_samples,
        }
        if settings.AUDIO_INPUT_DEVICE:
            stream_kwargs["device"] = settings.AUDIO_INPUT_DEVICE

        logger.info(
            "Starting continuous audio listener | sample_rate=%d | frame_ms=%d | vad_mode=%d",
            settings.AUDIO_SAMPLE_RATE,
            settings.AUDIO_FRAME_MS,
            settings.AUDIO_VAD_MODE,
        )

        try:
            with sd.RawInputStream(**stream_kwargs) as stream:
                logger.info("Continuous audio listener started")
                while not self._stop_event.is_set():
                    data, overflowed = stream.read(frame_samples)
                    if overflowed:
                        logger.warning("Audio input overflow detected")
                    for segment in segmenter.process_pcm_chunk(bytes(data)):
                        self._enqueue_segment(segment)
        except Exception:
            logger.exception("Continuous audio listener crashed")
        finally:
            tail_segment = segmenter.flush()
            if tail_segment:
                self._enqueue_segment(tail_segment)
            logger.info("Continuous audio listener stopped")

    def _enqueue_segment(self, segment: VADSegment):
        try:
            self.audio_queue.enqueue_pcm16(
                pcm_bytes=segment.pcm_bytes,
                sample_rate=settings.AUDIO_SAMPLE_RATE,
                metadata={
                    "source": "live_mic_vad",
                    "segment_reason": segment.reason,
                    "duration_ms": segment.duration_ms,
                },
            )
        except Exception:
            logger.exception("Failed to enqueue VAD segment")
