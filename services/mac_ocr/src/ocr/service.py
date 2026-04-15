from __future__ import annotations

from pathlib import Path

from common.models.ocr import OcrResponse
from common.utils.logs import get_logger

from .vision import _recognize_texts_from_path

log = get_logger("mac_ocr", "ocr")


def ocr_image_path(path: Path) -> OcrResponse:
    image_path = path.expanduser().resolve()
    log.debug("Starting OCR | path=%s", image_path)
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    texts = _recognize_texts_from_path(image_path)
    text = " ".join(texts).strip()
    log.debug(
        "Finished OCR | path=%s | text_count=%s | text_len=%s | text_preview=%r",
        image_path,
        len(texts),
        len(text),
        text[:200],
    )
    pages = (
        []
        if not text
        else [
            {
                "index": 0,
                "markdown": text,
                "images": [],
            }
        ]
    )
    return OcrResponse.model_validate(
        {
            "pages": pages,
            "model": "mac-ocr",
            "usage_info": {
                "pages_processed": 1,
                "doc_size_bytes": image_path.stat().st_size,
            },
            "document_annotation": None,
            "object": "ocr",
        }
    )
