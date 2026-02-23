import os

from dotenv import load_dotenv
from pydantic import BaseModel


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    REPO_ROOT: str = os.path.abspath(os.path.join(BASE_DIR, ".."))

    VAULT_PATH: str = os.getenv("VAULT_PATH", os.path.join(REPO_ROOT, "vault"))
    VAULT_PROMPTS_PATH: str = VAULT_PATH

    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "local")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")

    LLM_MODEL: str = os.getenv("LLM_MODEL", "local-gguf-model")
    LLM_MODEL_PATH: str = os.getenv("LLM_MODEL_PATH", "/models/model.gguf")
    LLM_CONTEXT_LENGTH: int = int(os.getenv("LLM_CONTEXT_LENGTH", "32768"))
    LLM_THREADS: int = int(os.getenv("LLM_THREADS", "6"))
    LLM_N_GPU_LAYERS: int = int(os.getenv("LLM_N_GPU_LAYERS", "30"))
    LLM_BATCH_SIZE: int = int(os.getenv("LLM_BATCH_SIZE", "512"))
    LLM_MAX_CONCURRENT_PREDICTIONS: int = int(
        os.getenv("LLM_MAX_CONCURRENT_PREDICTIONS", "4")
    )
    LLM_FLASH_ATTENTION: bool = _env_bool("LLM_FLASH_ATTENTION", True)
    LLM_USE_MMAP: bool = _env_bool("LLM_USE_MMAP", True)
    LLM_OFFLOAD_KQV: bool = _env_bool("LLM_OFFLOAD_KQV", True)
    LLM_SEED: int | None = (
        int(os.getenv("LLM_SEED")) if os.getenv("LLM_SEED") not in (None, "") else None
    )
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


def _load_repo_env(repo_root: str):
    dotenv_path = os.path.join(repo_root, ".env")
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path, override=False)


_load_repo_env(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
settings = Settings()


def init_vault():
    settings.VAULT_PATH = os.path.abspath(settings.VAULT_PATH)
    settings.VAULT_PROMPTS_PATH = settings.VAULT_PATH

    os.makedirs(settings.VAULT_PATH, exist_ok=True)


init_vault()
