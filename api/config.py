import os
from pydantic import BaseModel


class Settings(BaseModel):
    LM_STUDIO_URL: str = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1")
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    BRAIN_PATH: str = os.path.join(BASE_DIR, "second_brain")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemma-3n-e2b-it")
    LLM_CONTEXT_LENGTH: int = int(os.getenv("LLM_CONTEXT_LENGTH", "32768"))


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
