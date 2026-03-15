from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from exocort import settings


@dataclass(frozen=True)
class AudioConfig:
    source: str
    sample_rate: int
    frame_ms: int
    vad_mode: int
    start_rms: int
    continue_rms: int
    start_trigger_ms: int
    start_window_ms: int
    end_silence_ms: int
    pre_roll_ms: int
    min_segment_ms: int
    max_segment_ms: int
    input_device: str | None


@dataclass(frozen=True)
class AudioSegment:
    source: str
    pcm_bytes: bytes
    sample_rate: int
    duration_ms: int
    rms: int
    ended_by: str


@dataclass(frozen=True)
class Settings:
    enabled: bool
    api_audio_url: str
    spool_dir: Path
    request_timeout_s: float
    max_upload_per_cycle: int
    min_rms: int
    reconnect_delay_s: float
    audio: AudioConfig
    system_audio: AudioConfig | None

    @classmethod
    def from_env(cls) -> "Settings":
        from .device import detect_loopback_input_device_name

        system_device = settings.audio_capture_system_input_device()
        if system_device is None and settings.audio_capture_system_enabled():
            system_device = detect_loopback_input_device_name()

        sample_rate = settings.audio_capture_sample_rate()
        frame_ms = settings.audio_capture_frame_ms()
        return cls(
            enabled=settings.audio_capture_enabled(),
            api_audio_url=settings.collector_audio_url(),
            spool_dir=settings.audio_capture_spool_dir(),
            request_timeout_s=settings.audio_capture_request_timeout_s(),
            max_upload_per_cycle=settings.audio_capture_max_upload_per_cycle(),
            min_rms=settings.audio_capture_min_rms(),
            reconnect_delay_s=settings.audio_capture_reconnect_delay_s(),
            audio=AudioConfig(
                source="mic",
                sample_rate=sample_rate,
                frame_ms=frame_ms,
                vad_mode=settings.audio_capture_vad_mode(),
                start_rms=settings.audio_capture_start_rms(),
                continue_rms=settings.audio_capture_continue_rms(),
                start_trigger_ms=settings.audio_capture_start_trigger_ms(),
                start_window_ms=settings.audio_capture_start_window_ms(),
                end_silence_ms=settings.audio_capture_end_silence_ms(),
                pre_roll_ms=settings.audio_capture_pre_roll_ms(),
                min_segment_ms=settings.audio_capture_min_segment_ms(),
                max_segment_ms=settings.audio_capture_max_segment_ms(),
                input_device=settings.audio_capture_input_device(),
            ),
            system_audio=(
                AudioConfig(
                    source="system",
                    sample_rate=sample_rate,
                    frame_ms=frame_ms,
                    vad_mode=settings.audio_capture_system_vad_mode(),
                    start_rms=settings.audio_capture_system_start_rms(),
                    continue_rms=settings.audio_capture_system_continue_rms(),
                    start_trigger_ms=settings.audio_capture_system_start_trigger_ms(),
                    start_window_ms=settings.audio_capture_system_start_window_ms(),
                    end_silence_ms=settings.audio_capture_system_end_silence_ms(),
                    pre_roll_ms=settings.audio_capture_system_pre_roll_ms(),
                    min_segment_ms=settings.audio_capture_system_min_segment_ms(),
                    max_segment_ms=settings.audio_capture_system_max_segment_ms(),
                    input_device=system_device,
                )
                if system_device is not None
                else None
            ),
        )
