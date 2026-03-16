from __future__ import annotations

import logging
import platform
from pathlib import Path

import sounddevice as sd

log = logging.getLogger("audio_capture")

LOOPBACK_KEYWORDS = (
    "loopback",
    "blackhole",
    "soundflower",
    "vb-cable",
    "monitor",
    "mix",
    "pulse",
    "virtual",
    "stereo mix",
    "what u hear",
)

PREFERRED_MIC_KEYWORDS = (
    "microphone",
    "mic",
    "built-in",
    "internal",
    "macbook",
)
AVOID_MIC_KEYWORDS = (
    "iphone",
    "continuity",
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
) -> tuple[int | None, str, dict[str, object]]:
    system_devices = _list_system_capture_devices()
    input_devices = _list_input_devices()
    devices = system_devices if source == "system" else input_devices

    if requested_device:
        exact = _match_input_device(devices, requested_device, exact=True)
        if exact is not None:
            return _resolved_device(exact)

        partial = _match_input_device(devices, requested_device, exact=False)
        if partial is not None:
            log.warning(
                "Input device %r was not an exact match; using %s",
                requested_device,
                partial[1],
            )
            return _resolved_device(partial)

        log.warning(
            "Input device %r was not found for %s source; falling back to auto/default input",
            requested_device,
            source,
        )

    if source == "system":
        detected = _detect_loopback_input_device(devices)
        if detected is not None:
            return _resolved_device(detected)
        wasapi_default = _resolve_windows_default_loopback()
        if wasapi_default is not None:
            return wasapi_default
        return None, "system-unavailable", {"system_unavailable": True}

    preferred_mic = _detect_preferred_microphone(input_devices)
    if preferred_mic is not None:
        return _resolved_device(preferred_mic)
    return None, "default", {}


def _list_input_devices() -> list[tuple[int, str]]:
    devices: list[tuple[int, str]] = []
    for index, device in enumerate(sd.query_devices()):
        if int(device.get("max_input_channels", 0) or 0) <= 0:
            continue
        devices.append((index, str(device.get("name", f"device-{index}"))))
    return devices


def _list_system_capture_devices() -> list[tuple[int, str]]:
    devices = _list_input_devices()
    if platform.system().lower() != "windows":
        return devices
    query = sd.query_devices()
    for index, device in enumerate(query):
        if int(device.get("max_output_channels", 0) or 0) <= 0:
            continue
        hostapi_name = _device_hostapi_name(index)
        if "wasapi" not in hostapi_name.lower():
            continue
        name = str(device.get("name", f"device-{index}"))
        devices.append((index, f"{name} (loopback)"))
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


def _detect_preferred_microphone(
    devices: list[tuple[int, str]],
) -> tuple[int, str] | None:
    for index, name in devices:
        candidate = name.lower()
        if any(word in candidate for word in AVOID_MIC_KEYWORDS):
            continue
        if any(word in candidate for word in PREFERRED_MIC_KEYWORDS):
            return index, name
    return None


def _device_hostapi_name(index: int) -> str:
    try:
        device = sd.query_devices(index)
        hostapi_index = int(device.get("hostapi", -1) or -1)
        hostapis = sd.query_hostapis()
        if 0 <= hostapi_index < len(hostapis):
            return str(hostapis[hostapi_index].get("name", ""))
    except Exception:
        return ""
    return ""


def _resolved_device(device: tuple[int, str]) -> tuple[int, str, dict[str, object]]:
    index, label = device
    if "(loopback)" in label.lower():
        wasapi_settings = getattr(sd, "WasapiSettings", None)
        if wasapi_settings is not None:
            return index, label, {"extra_settings": wasapi_settings(loopback=True)}
    return index, label, {}


def _resolve_windows_default_loopback() -> tuple[int, str, dict[str, object]] | None:
    if platform.system().lower() != "windows":
        return None
    wasapi_settings = getattr(sd, "WasapiSettings", None)
    if wasapi_settings is None:
        return None
    try:
        default_output_index = int(sd.default.device[1])  # type: ignore[index]
        if default_output_index < 0:
            return None
        output = sd.query_devices(default_output_index)
        if int(output.get("max_output_channels", 0) or 0) <= 0:
            return None
        hostapi_name = _device_hostapi_name(default_output_index)
        if "wasapi" not in hostapi_name.lower():
            return None
        label = f"{output.get('name', f'device-{default_output_index}')} (loopback default output)"
        return default_output_index, str(label), {
            "extra_settings": wasapi_settings(loopback=True)
        }
    except Exception:
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
