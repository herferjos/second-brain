import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _env_int(name: str, default: int | None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


# Collector

def collector_data_dir() -> Path:
    return Path(_env_str("COLLECTOR_DATA_DIR", "data")).expanduser().resolve()


def collector_host() -> str:
    return _env_str("COLLECTOR_HOST", "127.0.0.1")


def collector_port() -> int:
    return int(_env_int("COLLECTOR_PORT", 8787) or 8787)


def collector_base_url() -> str:
    base = _env_str("COLLECTOR_BASE_URL", "")
    if base:
        return base.rstrip("/")
    return f"http://{collector_host()}:{collector_port()}"


def collector_events_url() -> str:
    return _env_str("COLLECTOR_EVENTS_URL", f"{collector_base_url()}/events")


def collector_audio_url() -> str:
    return _env_str("COLLECTOR_AUDIO_URL", f"{collector_base_url()}/audio")


def collector_frame_url() -> str:
    return _env_str("COLLECTOR_FRAME_URL", f"{collector_base_url()}/frame")


# Audio capture

def audio_capture_enabled() -> bool:
    raw = _env_str("AUDIO_CAPTURE_ENABLED", "")
    if raw:
        return raw.lower() in {"1", "true", "yes", "on"}
    return _env_str("AUDIO_BRIDGE_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def audio_capture_input_device() -> str | None:
    raw = _env_str("AUDIO_CAPTURE_INPUT_DEVICE", "")
    if raw:
        return raw
    raw = _env_str("AUDIO_BRIDGE_INPUT_DEVICE", "")
    return raw or None


def audio_capture_system_enabled() -> bool:
    return _env_bool("AUDIO_CAPTURE_SYSTEM_ENABLED", False)


def audio_capture_system_input_device() -> str | None:
    raw = _env_str("AUDIO_CAPTURE_SYSTEM_DEVICE", "")
    return raw or None


def audio_capture_spool_dir() -> Path:
    raw = _env_str("AUDIO_CAPTURE_SPOOL_DIR", "") or _env_str("AUDIO_BRIDGE_SPOOL_DIR", "data/spool/audio")
    return Path(raw).expanduser().resolve()


def audio_capture_sample_rate() -> int:
    return int(_env_int("AUDIO_CAPTURE_SAMPLE_RATE", 0) or _env_int("AUDIO_BRIDGE_SAMPLE_RATE", 16000) or 16000)


def audio_capture_frame_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_FRAME_MS", 0) or _env_int("AUDIO_BRIDGE_FRAME_MS", 20) or 20)


def audio_capture_vad_mode() -> int:
    if os.getenv("AUDIO_CAPTURE_VAD_MODE") is not None:
        return int(_env_int("AUDIO_CAPTURE_VAD_MODE", 2) or 2)
    return int(_env_int("AUDIO_BRIDGE_VAD_MODE", 2) or 2)


def audio_capture_start_rms() -> int:
    return int(_env_int("AUDIO_CAPTURE_START_RMS", 250) or 250)


def audio_capture_continue_rms() -> int:
    return int(_env_int("AUDIO_CAPTURE_CONTINUE_RMS", 180) or 180)


def audio_capture_start_trigger_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_START_TRIGGER_MS", 0) or _env_int("AUDIO_BRIDGE_START_TRIGGER_MS", 240) or 240)


def audio_capture_start_window_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_START_WINDOW_MS", 0) or _env_int("AUDIO_BRIDGE_START_WINDOW_MS", 400) or 400)


def audio_capture_end_silence_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_END_SILENCE_MS", 0) or _env_int("AUDIO_BRIDGE_END_SILENCE_MS", 900) or 900)


def audio_capture_pre_roll_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_PRE_ROLL_MS", 0) or _env_int("AUDIO_BRIDGE_PRE_ROLL_MS", 300) or 300)


def audio_capture_min_segment_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_MIN_SEGMENT_MS", 0) or _env_int("AUDIO_BRIDGE_MIN_SEGMENT_MS", 1000) or 1000)


def audio_capture_max_segment_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_MAX_SEGMENT_MS", 0) or _env_int("AUDIO_BRIDGE_MAX_SEGMENT_MS", 30000) or 30000)


def audio_capture_system_vad_mode() -> int:
    return int(_env_int("AUDIO_CAPTURE_SYSTEM_VAD_MODE", 1) or 1)


def audio_capture_system_start_rms() -> int:
    return int(_env_int("AUDIO_CAPTURE_SYSTEM_START_RMS", 180) or 180)


def audio_capture_system_continue_rms() -> int:
    return int(_env_int("AUDIO_CAPTURE_SYSTEM_CONTINUE_RMS", 120) or 120)


def audio_capture_system_start_trigger_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_SYSTEM_START_TRIGGER_MS", 90) or 90)


def audio_capture_system_start_window_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_SYSTEM_START_WINDOW_MS", 300) or 300)


def audio_capture_system_end_silence_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_SYSTEM_END_SILENCE_MS", 900) or 900)


def audio_capture_system_pre_roll_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_SYSTEM_PRE_ROLL_MS", 300) or 300)


def audio_capture_system_min_segment_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_SYSTEM_MIN_SEGMENT_MS", 500) or 500)


def audio_capture_system_max_segment_ms() -> int:
    return int(_env_int("AUDIO_CAPTURE_SYSTEM_MAX_SEGMENT_MS", 15000) or 15000)


def audio_capture_request_timeout_s() -> float:
    return float(_env_float("AUDIO_CAPTURE_REQUEST_TIMEOUT_S", 0) or _env_float("AUDIO_BRIDGE_REQUEST_TIMEOUT_S", 20.0) or 20.0)


def audio_capture_reconnect_delay_s() -> float:
    return max(0.2, _env_float("AUDIO_CAPTURE_RECONNECT_DELAY_S", 1.0))


def audio_capture_max_upload_per_cycle() -> int:
    return int(_env_int("AUDIO_CAPTURE_MAX_UPLOAD_PER_CYCLE", 0) or _env_int("AUDIO_BRIDGE_MAX_UPLOAD_PER_CYCLE", 10) or 10)


def audio_capture_min_rms() -> int:
    return int(_env_int("AUDIO_CAPTURE_MIN_RMS", 0) or _env_int("AUDIO_BRIDGE_MIN_RMS", 200) or 200)


def audio_capture_log_level() -> str:
    return _env_str("AUDIO_CAPTURE_LOG_LEVEL", _env_str("AUDIO_BRIDGE_LOG_LEVEL", "INFO"))


def audio_capture_api_audio_url() -> str:
    return _env_str("AUDIO_CAPTURE_API_AUDIO_URL", _env_str("AUDIO_BRIDGE_API_AUDIO_URL", collector_audio_url()))


# Screen capture

def screen_capture_enabled() -> bool:
    return _env_bool("SCREEN_CAPTURE_ENABLED", False)


def screen_capture_fps() -> float:
    return max(0.1, _env_float("SCREEN_CAPTURE_FPS", 1.0))


def screen_capture_monitor_index() -> int:
    return max(1, int(_env_int("SCREEN_CAPTURE_MONITOR_INDEX", 1) or 1))


def screen_capture_save_png() -> bool:
    return _env_bool("SCREEN_CAPTURE_SAVE_PNG", False)


def screen_capture_prompt_permission() -> bool:
    return _env_bool("SCREEN_CAPTURE_PROMPT_PERMISSION", False)


def screen_capture_out_dir() -> Path:
    return Path(_env_str("SCREEN_CAPTURE_OUT_DIR", "screen_capture/debug_output")).expanduser()


def screen_capture_request_timeout_s() -> float:
    return _env_float("SCREEN_CAPTURE_REQUEST_TIMEOUT_S", 15.0)


def screen_capture_log_level() -> str:
    return _env_str("SCREEN_CAPTURE_LOG_LEVEL", "INFO")


# Processor / LLM

def data_dir() -> Path:
    return Path(_env_str("PROCESSOR_DATA_DIR", "data")).expanduser().resolve()


def vault_dir() -> Path:
    return Path(_env_str("PROCESSOR_VAULT_DIR", "vault")).expanduser().resolve()


# Engine config (single unified file)

def engine_config_path() -> Path:
    return Path(
        _env_str("ENGINE_CONFIG_PATH", "config/examples/engine.config.json")
    ).expanduser().resolve()


def max_events_per_run() -> int | None:
    return _env_int("PROCESSOR_MAX_EVENTS_PER_RUN", None)


def overwrite() -> bool:
    return _env_bool("PROCESSOR_OVERWRITE", False)


def processor_enabled() -> bool:
    return _env_bool("PROCESSOR_ENABLED", False)
