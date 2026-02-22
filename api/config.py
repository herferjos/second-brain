import os
from pydantic import BaseModel


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    BRAIN_PATH: str = os.path.join(BASE_DIR, "second_brain")
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
    AUDIO_AUTO_LISTEN: bool = _env_bool("AUDIO_AUTO_LISTEN", False)
    AUDIO_INPUT_DEVICE: str | None = os.getenv("AUDIO_INPUT_DEVICE") or None
    AUDIO_SAMPLE_RATE: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    AUDIO_CHANNELS: int = int(os.getenv("AUDIO_CHANNELS", "1"))
    AUDIO_FRAME_MS: int = int(os.getenv("AUDIO_FRAME_MS", "20"))
    AUDIO_VAD_MODE: int = int(os.getenv("AUDIO_VAD_MODE", "2"))
    AUDIO_VAD_START_TRIGGER_MS: int = int(os.getenv("AUDIO_VAD_START_TRIGGER_MS", "240"))
    AUDIO_VAD_START_WINDOW_MS: int = int(os.getenv("AUDIO_VAD_START_WINDOW_MS", "400"))
    AUDIO_VAD_END_SILENCE_MS: int = int(os.getenv("AUDIO_VAD_END_SILENCE_MS", "900"))
    AUDIO_VAD_PRE_ROLL_MS: int = int(os.getenv("AUDIO_VAD_PRE_ROLL_MS", "300"))
    AUDIO_VAD_MIN_SEGMENT_MS: int = int(os.getenv("AUDIO_VAD_MIN_SEGMENT_MS", "1000"))
    AUDIO_VAD_MAX_SEGMENT_MS: int = int(os.getenv("AUDIO_VAD_MAX_SEGMENT_MS", "30000"))
    AUDIO_QUEUE_DIR: str = os.getenv("AUDIO_QUEUE_DIR", "temp/spool_audio")
    AUDIO_QUEUE_MAX_SIZE: int = int(os.getenv("AUDIO_QUEUE_MAX_SIZE", "200"))
    AUDIO_WORKER_POLL_SECONDS: float = float(os.getenv("AUDIO_WORKER_POLL_SECONDS", "1.0"))
    AUDIO_FLUSH_MAX_WAIT_SECONDS: float = float(
        os.getenv("AUDIO_FLUSH_MAX_WAIT_SECONDS", "60")
    )
    AUDIO_FLUSH_MIN_WORDS: int = int(os.getenv("AUDIO_FLUSH_MIN_WORDS", "100"))
    AUDIO_FLUSH_SILENCE_GAP_SECONDS: float = float(
        os.getenv("AUDIO_FLUSH_SILENCE_GAP_SECONDS", "4")
    )
    AUDIO_MAX_BATCH_SEGMENTS: int = int(os.getenv("AUDIO_MAX_BATCH_SEGMENTS", "8"))
    AUDIO_MAX_RETRIES: int = int(os.getenv("AUDIO_MAX_RETRIES", "3"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()

# Structure according to MASTER SPEC (updated)
BRAIN_STRUCTURE = [
    "00_inbox",
    "01_core",
    "02_areas",
    "03_projects",
    "04_knowledge",
    "05_skills",
    "06_decisions",
    "07_lab",
    "08_reflections",
    "09_failures",
    "10_network",
    "11_resources",
    "12_log",
]

# Files inside 01_core (managed manually or by specific skills)
CORE_FILES = {"01_core": ["identity.md", "values.md", "principles.md", "strategy.md"]}


def init_brain():
    if not os.path.exists(settings.BRAIN_PATH):
        os.makedirs(settings.BRAIN_PATH)

    # Create main folder structure
    for folder in BRAIN_STRUCTURE:
        path = os.path.join(settings.BRAIN_PATH, folder)
        if not os.path.exists(path):
            os.makedirs(path)

    # Initialize Core Files
    for folder, files in CORE_FILES.items():
        folder_path = os.path.join(settings.BRAIN_PATH, folder)
        if os.path.exists(folder_path):
            for filename in files:
                path = os.path.join(folder_path, filename)
                if not os.path.exists(path):
                    title = filename.replace(".md", "").upper()
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(
                            f"# {title}\n\nCore definition file. Initialize with your data.\n"
                        )


init_brain()
