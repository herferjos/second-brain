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
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def data_dir() -> Path:
    return Path(_env_str("PROCESSOR_DATA_DIR", "data")).expanduser().resolve()


def vault_dir() -> Path:
    return Path(_env_str("PROCESSOR_VAULT_DIR", "vault")).expanduser().resolve()


def llm_provider() -> str:
    return _env_str("LLM_PROVIDER", "llama_cpp").lower()


def llm_model_path() -> str:
    return _env_str("LLM_MODEL_PATH", "").strip()


def llm_context_length() -> int:
    v = _env_int("LLM_CONTEXT_LENGTH", 4096)
    return v if v is not None else 4096


def llm_n_gpu_layers() -> int:
    v = _env_int("LLM_N_GPU_LAYERS", -1)
    return v if v is not None else -1


def llm_threads() -> int:
    v = _env_int("LLM_THREADS", 4)
    return v if v is not None else 4


def llm_batch_size() -> int:
    v = _env_int("LLM_BATCH_SIZE", 512)
    return v if v is not None else 512


def llm_flash_attention() -> bool:
    return _env_bool("LLM_FLASH_ATTENTION", False)


def llm_use_mmap() -> bool:
    return _env_bool("LLM_USE_MMAP", True)


def llm_offload_kqv() -> bool:
    return _env_bool("LLM_OFFLOAD_KQV", False)


def llm_seed() -> int | None:
    return _env_int("LLM_SEED", None)


def llm_max_tokens() -> int:
    v = _env_int("LLM_MAX_TOKENS", 4096)
    return v if v is not None else 4096


def llm_temperature() -> float:
    return _env_float("LLM_TEMPERATURE", 0.3)


def llm_max_retries() -> int:
    v = _env_int("LLM_MAX_RETRIES", 3)
    return v if v is not None and v >= 1 else 3


def openai_api_key() -> str:
    return _env_str("OPENAI_API_KEY", "")


def openai_base_url() -> str:
    return _env_str("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def openai_model() -> str:
    return _env_str("OPENAI_MODEL", "gpt-4o-mini")


def gemini_api_key() -> str:
    return _env_str("GEMINI_API_KEY", "")


def gemini_model() -> str:
    return _env_str("GEMINI_MODEL", "gemini-2.0-flash")


def llm_concurrency() -> int:
    v = _env_int("LLM_CONCURRENCY", 1)
    return v if v is not None else 1



def max_events_per_run() -> int | None:
    return _env_int("PROCESSOR_MAX_EVENTS_PER_RUN", None)


def overwrite() -> bool:
    return _env_bool("PROCESSOR_OVERWRITE", False)
