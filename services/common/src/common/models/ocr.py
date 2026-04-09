from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OcrDocumentPayload(BaseModel):
    type: Literal["image_url"]
    image_url: str

    model_config = ConfigDict(extra="allow")


class OcrPageImage(BaseModel):
    id: str | None = None
    top_left_x: float | None = None
    top_left_y: float | None = None
    bottom_right_x: float | None = None
    bottom_right_y: float | None = None
    image_base64: str | None = None
    image_annotation: dict[str, object] | None = None

    model_config = ConfigDict(extra="allow")


class OcrPageTable(BaseModel):
    id: str | None = None
    markdown: str | None = None
    html: str | None = None
    table_annotation: dict[str, object] | None = None

    model_config = ConfigDict(extra="allow")


class OcrPageHyperlink(BaseModel):
    text: str | None = None
    url: str | None = None

    model_config = ConfigDict(extra="allow")


class OcrPageDimensions(BaseModel):
    width: int | None = None
    height: int | None = None
    dpi: int | None = None

    model_config = ConfigDict(extra="allow")


class OcrConfidenceScores(BaseModel):
    average_page_confidence_score: float | None = None
    minimum_page_confidence_score: float | None = None
    word_confidence_scores: list[dict[str, object]] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class OcrRequestPayload(BaseModel):
    model: str | None = None
    document: OcrDocumentPayload

    model_config = ConfigDict(extra="allow")


class OcrPage(BaseModel):
    index: int
    markdown: str
    images: list[OcrPageImage] = Field(default_factory=list)
    tables: list[OcrPageTable] = Field(default_factory=list)
    hyperlinks: list[OcrPageHyperlink] = Field(default_factory=list)
    header: str | None = None
    footer: str | None = None
    dimensions: OcrPageDimensions | None = None
    confidence_scores: OcrConfidenceScores | None = None

    model_config = ConfigDict(extra="allow")


class OcrUsageInfo(BaseModel):
    pages_processed: int
    doc_size_bytes: int | None = None

    model_config = ConfigDict(extra="allow")


class OcrResponse(BaseModel):
    pages: list[OcrPage]
    model: Literal["mac-ocr"]
    usage_info: OcrUsageInfo
    document_annotation: dict[str, object] | None = None
    object: Literal["ocr"]

    model_config = ConfigDict(extra="allow")


__all__ = [
    "OcrConfidenceScores",
    "OcrDocumentPayload",
    "OcrPageDimensions",
    "OcrPageHyperlink",
    "OcrPage",
    "OcrPageImage",
    "OcrPageTable",
    "OcrRequestPayload",
    "OcrResponse",
    "OcrUsageInfo",
]
