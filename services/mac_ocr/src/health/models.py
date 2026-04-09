from __future__ import annotations

from pydantic import BaseModel


class OcrHealthResponse(BaseModel):
    ok: bool = True

