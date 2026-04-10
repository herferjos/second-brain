from __future__ import annotations

from pathlib import Path
from typing import Any
import tomllib

from exocort.capturer.audio.vad import AudioVADConfig

from .models import (
    AudioSettings,
    EndpointSettings,
    ExocortSettings,
    ProcessorSettings,
    ScreenSettings,
)


def load_config(path: str | Path) -> ExocortSettings:
    config_path = Path(path)
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return parse_config(raw, base_dir=config_path.parent)


def parse_config(raw: dict[str, Any], base_dir: Path | None = None) -> ExocortSettings:
    base_dir = base_dir or Path.cwd()
    audio_raw = _get_table(raw, "audio")
    vad_raw = _get_table(audio_raw, "vad")
    screen_raw = _get_table(raw, "screen")
    processor_raw = _get_table(raw, "processor")
    processor_ocr_raw = _get_table(processor_raw, "ocr")
    processor_asr_raw = _get_table(processor_raw, "asr")

    return ExocortSettings(
        audio=AudioSettings(
            enabled=bool(audio_raw.get("enabled", False)),
            chunk_seconds=int(audio_raw.get("chunk_seconds", AudioSettings.chunk_seconds)),
            sample_rate=int(audio_raw.get("sample_rate", AudioSettings.sample_rate)),
            channels=int(audio_raw.get("channels", AudioSettings.channels)),
            output_dir=_resolve_path(
                audio_raw.get("output_dir"),
                base_dir,
                base_dir / "captures" / "audio",
            ),
            vad=AudioVADConfig(
                enabled=bool(vad_raw.get("enabled", AudioVADConfig.enabled)),
                aggressiveness=int(vad_raw.get("aggressiveness", AudioVADConfig.aggressiveness)),
                frame_ms=int(vad_raw.get("frame_ms", AudioVADConfig.frame_ms)),
                pre_roll_seconds=float(
                    vad_raw.get("pre_roll_seconds", AudioVADConfig.pre_roll_seconds)
                ),
                min_speech_seconds=float(
                    vad_raw.get("min_speech_seconds", AudioVADConfig.min_speech_seconds)
                ),
                min_silence_seconds=float(
                    vad_raw.get("min_silence_seconds", AudioVADConfig.min_silence_seconds)
                ),
            ),
        ),
        screen=ScreenSettings(
            enabled=bool(screen_raw.get("enabled", False)),
            interval_seconds=int(
                screen_raw.get("interval_seconds", ScreenSettings.interval_seconds)
            ),
            output_dir=_resolve_path(
                screen_raw.get("output_dir"),
                base_dir,
                base_dir / "captures" / "screen",
            ),
        ),
        processor=ProcessorSettings(
            enabled=bool(processor_raw.get("enabled", False)),
            watch_dir=_resolve_path(
                processor_raw.get("watch_dir"),
                base_dir,
                base_dir / "captures",
            ),
            output_dir=_resolve_path(
                processor_raw.get("output_dir"),
                base_dir,
                base_dir / "captures" / "processed",
            ),
            ocr=EndpointSettings(
                model=str(processor_ocr_raw.get("model", "")),
                api_base=str(processor_ocr_raw.get("api_base", "")),
                api_key_env=str(processor_ocr_raw.get("api_key_env", "")),
            ),
            asr=EndpointSettings(
                model=str(processor_asr_raw.get("model", "")),
                api_base=str(processor_asr_raw.get("api_base", "")),
                api_key_env=str(processor_asr_raw.get("api_key_env", "")),
            ),
        ),
    )


def _get_table(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{key}' must be a table/object.")
    return value


def _resolve_path(value: Any | None, base_dir: Path, default: Path) -> Path:
    if value is None:
        resolved = default
    else:
        resolved = Path(value)
        if not resolved.is_absolute():
            resolved = base_dir / resolved
    return resolved.expanduser().resolve()


__all__ = [
    "AudioSettings",
    "EndpointSettings",
    "ExocortSettings",
    "ProcessorSettings",
    "ScreenSettings",
    "load_config",
    "parse_config",
]
