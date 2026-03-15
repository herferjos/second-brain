from __future__ import annotations

import logging
import time
from threading import Event, Thread

import sounddevice as sd

from .device import resolve_input_device
from .models import AudioConfig, AudioSegment, Settings
from .uploader import SpoolUploader
from .vad import VadSegmenter

log = logging.getLogger("audio_capture")


class AudioCaptureAgent:
    def __init__(self, settings_obj: Settings):
        self.settings = settings_obj
        self.uploader = SpoolUploader(settings_obj)
        self.stop_event = Event()

    def run(self) -> None:
        if not self.settings.enabled:
            log.info("Audio capture disabled (set AUDIO_CAPTURE_ENABLED=1 to enable).")
            return

        sources = [self.settings.audio]
        if self.settings.system_audio is not None:
            sources.append(self.settings.system_audio)

        self.uploader.flush_pending(max_files=10_000)
        threads = [
            Thread(
                target=self._run_source,
                args=(source,),
                name=f"audio-capture-{source.source}",
                daemon=True,
            )
            for source in sources
        ]

        log.info(
            "Starting audio capture | collector_audio_url=%s | sources=%s",
            self.settings.api_audio_url,
            [source.source for source in sources],
        )

        for thread in threads:
            thread.start()

        try:
            while any(thread.is_alive() for thread in threads):
                time.sleep(0.5)
        except KeyboardInterrupt:
            log.info("Stopping audio capture by user request")
        finally:
            self.stop_event.set()
            for thread in threads:
                thread.join(timeout=5.0)
            self.uploader.flush_pending(max_files=10_000)
            log.info("Audio capture stopped")

    def _run_source(self, config: AudioConfig) -> None:
        while not self.stop_event.is_set():
            try:
                listen_microphone(
                    config,
                    self._handle_segment,
                    stop_event=self.stop_event,
                )
            except Exception:
                log.exception("Audio source failed | source=%s", config.source)
                self.stop_event.wait(self.settings.reconnect_delay_s)

    def _handle_segment(self, segment: AudioSegment) -> bool:
        if segment.rms < self.settings.min_rms:
            log.info(
                "Segment dropped (silent) | source=%s | duration_ms=%d | ended_by=%s | min_rms=%d",
                segment.source,
                segment.duration_ms,
                segment.ended_by,
                self.settings.min_rms,
            )
            return not self.stop_event.is_set()

        saved = self.uploader.save_segment(segment)
        log.info(
            "Segment queued | source=%s | file=%s | duration_ms=%d | ended_by=%s",
            segment.source,
            saved.name,
            segment.duration_ms,
            segment.ended_by,
        )
        self.uploader.flush_pending(max_files=self.settings.max_upload_per_cycle)
        return not self.stop_event.is_set()


def listen_microphone(
    config: AudioConfig,
    on_segment,
    *,
    stop_event: Event | None = None,
    idle_timeout_s: float | None = None,
) -> None:
    frame_samples = int(config.sample_rate * config.frame_ms / 1000)
    resolved_device, resolved_label = resolve_input_device(
        requested_device=config.input_device,
        source=config.source,
    )
    stream_kwargs: dict[str, object] = {
        "samplerate": config.sample_rate,
        "channels": 1,
        "dtype": "int16",
        "blocksize": frame_samples,
    }
    if resolved_device is not None:
        stream_kwargs["device"] = resolved_device

    segmenter = VadSegmenter(config)
    started_at = time.monotonic()

    log.info(
        "Opening %s audio | sample_rate=%d | frame_ms=%d | vad_mode=%d | device=%s",
        config.source,
        config.sample_rate,
        config.frame_ms,
        config.vad_mode,
        resolved_label,
    )

    with sd.RawInputStream(**stream_kwargs) as stream:
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            if (
                idle_timeout_s is not None
                and (time.monotonic() - started_at) >= idle_timeout_s
            ):
                break

            data, overflowed = stream.read(frame_samples)
            if overflowed:
                log.warning("Audio input overflow detected | source=%s", config.source)

            for segment in segmenter.feed(bytes(data)):
                if on_segment(segment) is False:
                    return

        tail = segmenter.flush()
        if tail is not None:
            on_segment(tail)


def capture_once(config: AudioConfig, timeout_s: float) -> AudioSegment | None:
    captured: list[AudioSegment] = []

    def on_segment(segment: AudioSegment) -> bool:
        captured.append(segment)
        return False

    listen_microphone(config, on_segment, idle_timeout_s=timeout_s)
    return captured[0] if captured else None
