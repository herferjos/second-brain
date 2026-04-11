from __future__ import annotations

import base64
import binascii
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import HTTPException

from common.utils.logs import get_logger

from common.models.ocr import OcrDocumentPayload

log = get_logger("mac_ocr", "document")


def resolve_document_path(document: OcrDocumentPayload) -> Path:
    image_url = document.image_url
    log.debug(
        "Resolving OCR document | type=%s | image_url_prefix=%s",
        document.type,
        image_url[:64],
    )
    if not image_url.startswith("data:"):
        raise HTTPException(status_code=400, detail="document.image_url must be a data URI.")

    try:
        header, encoded = image_url.split(",", 1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid document.image_url data URI.") from exc

    if ";base64" not in header:
        raise HTTPException(
            status_code=400,
            detail="document.image_url must be base64 encoded.",
        )

    mime_type = header[5:].split(";", 1)[0]
    log.debug("Parsed OCR data URI | mime_type=%s", mime_type)
    suffix = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
    }.get(mime_type, ".img")

    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 image data.") from exc
    log.debug("Decoded OCR image bytes | byte_count=%s", len(image_bytes))

    temp_file = NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        temp_file.write(image_bytes)
    finally:
        temp_file.close()

    log.debug("Stored OCR temp image | path=%s | suffix=%s", temp_file.name, suffix)

    return Path(temp_file.name)
