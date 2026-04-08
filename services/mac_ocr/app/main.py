from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.api import api_router
from src.config import HOST, PORT

app = FastAPI(title="Mac OCR", version="0.1.0")
app.include_router(api_router)


def main() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
