from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class OcrPage:
    index: int
    markdown: str


@dataclass(slots=True, frozen=True)
class OcrResponse:
    pages: tuple[OcrPage, ...]
