from __future__ import annotations

from pydantic import BaseModel


class AsrHealthResponse(BaseModel):
    ok: bool = True
    locale: str | None = None
    speech_permission: bool

