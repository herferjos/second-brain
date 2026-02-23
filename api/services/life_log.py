import json
import os
from datetime import datetime

from api.config import settings

LOG_DIR = os.path.join(settings.VAULT_PATH, "_logs")


def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _today_file() -> str:
    return os.path.join(LOG_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.jsonl")


def append_entry(entry_type: str, summary: str, metadata: dict = None):
    _ensure_log_dir()

    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": entry_type,
        "summary": summary,
        "metadata": metadata or {},
    }

    with open(_today_file(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
