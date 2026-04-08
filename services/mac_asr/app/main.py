from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.api import api_router
from src.asr import ensure_speech_permission
from src.config import HOST, PORT, PROMPT_PERMISSION

app = FastAPI(title="Mac ASR", version="0.1.0")
app.include_router(api_router)


def main() -> None:
    import uvicorn

    if not ensure_speech_permission(prompt=PROMPT_PERMISSION):
        raise RuntimeError("Speech recognition permission is required.")
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
