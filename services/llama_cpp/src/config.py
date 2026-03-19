from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _str(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _int(key: str, default: int) -> int:
    raw = os.getenv(key, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def _float(key: str, default: float) -> float:
    raw = os.getenv(key, str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class LlamaCppSettings:
    host: str
    port: int
    model_id: str | None
    model_path: Path | None
    model_file: str | None
    model_dir: Path
    revision: str | None
    n_ctx: int
    n_gpu_layers: int
    n_threads: int
    temperature: float


def load_settings() -> LlamaCppSettings:
    model_path_raw = _str("LLAMA_CPP_MODEL_PATH", "")
    model_path = Path(model_path_raw).expanduser().resolve() if model_path_raw else None
    model_dir_raw = _str("LLAMA_CPP_MODEL_DIR", "")
    model_dir = Path(model_dir_raw).expanduser().resolve() if model_dir_raw else Path.cwd() / "models"
    model_id = _str("LLAMA_CPP_MODEL_ID", "") or None
    model_file = _str("LLAMA_CPP_MODEL_FILE", "") or None
    revision = _str("LLAMA_CPP_REVISION", "") or None
    return LlamaCppSettings(
        host=_str("LLAMA_CPP_HOST", "127.0.0.1"),
        port=_int("LLAMA_CPP_PORT", 9100),
        model_id=model_id,
        model_path=model_path,
        model_file=model_file,
        model_dir=model_dir,
        revision=revision,
        n_ctx=_int("LLAMA_CPP_CTX", 4096),
        n_gpu_layers=_int("LLAMA_CPP_N_GPU_LAYERS", 0),
        n_threads=_int("LLAMA_CPP_THREADS", 0),
        temperature=_float("LLAMA_CPP_TEMPERATURE", 0.2),
    )
