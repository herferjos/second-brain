from __future__ import annotations

import logging
from pathlib import Path

import sounddevice as sd

log = logging.getLogger("audio_capture")

LOOPBACK_KEYWORDS = (
    "loopback",
    "vb-cable",
    "stereo mix",
    "what u hear",
)


def detect_loopback_input_device_name() -> str | None:
    detected = _detect_loopback_input_device(_list_input_devices())
    if detected is None:
        return None
    return detected[1]


def resolve_input_device(
    *,
    requested_device: str | None,
    source: str,
) -> tuple[int | None, str]:
    devices = _list_input_devices()

    if requested_device:
        exact = _match_input_device(devices, requested_device, exact=True)
        if exact is not None:
            return exact

        partial = _match_input_device(devices, requested_device, exact=False)
        if partial is not None:
            log.warning(
                "Input device %r was not an exact match; using %s",
                requested_device,
                partial[1],
            )
            return partial

        log.warning(
            "Input device %r was not found for %s source; falling back to auto/default input",
            requested_device,
            source,
        )

    if source == "system":
        detected = _detect_loopback_input_device(devices)
        if detected is not None:
            return detected

    return None, "default"


def _list_input_devices() -> list[tuple[int, str]]:
    devices: list[tuple[int, str]] = []
    for index, device in enumerate(sd.query_devices()):
        if int(device.get("max_input_channels", 0) or 0) <= 0:
            continue
        devices.append((index, str(device.get("name", f"device-{index}"))))
    return devices


def _match_input_device(
    devices: list[tuple[int, str]],
    requested_device: str,
    *,
    exact: bool,
) -> tuple[int, str] | None:
    requested = requested_device.strip().lower()
    if not requested:
        return None

    if requested.isdigit():
        requested_index = int(requested)
        for index, name in devices:
            if index == requested_index:
                return index, name
        return None

    for index, name in devices:
        candidate = name.lower()
        if exact and candidate == requested:
            return index, name
        if not exact and requested in candidate:
            return index, name
    return None


def _detect_loopback_input_device(
    devices: list[tuple[int, str]],
) -> tuple[int, str] | None:
    for index, name in devices:
        candidate = name.lower()
        if any(keyword in candidate for keyword in LOOPBACK_KEYWORDS):
            log.info("Detected loopback input device automatically: %s", name)
            return index, name
    return None


def _pcm_rms(pcm_bytes: bytes) -> int:
    import audioop

    if not pcm_bytes:
        return 0
    return int(audioop.rms(pcm_bytes, 2))


def wav_rms(path: Path) -> int:
    import wave

    try:
        with wave.open(str(path), "rb") as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
        return _pcm_rms(frames)
    except Exception:
        return 0


def remove_wav_and_meta(path: Path, logger: logging.Logger) -> bool:
    meta = path.with_suffix(".wav.meta.json")
    try:
        path.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        return True
    except OSError:
        logger.exception("Failed to remove file | file=%s", path.name)
        return False
