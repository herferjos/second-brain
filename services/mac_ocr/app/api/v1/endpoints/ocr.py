from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.document import OcrRequestPayload, resolve_document_path
from common.logs import get_logger
from src.ocr import ocr_image_path

router = APIRouter()
log = get_logger("mac_ocr", "api")


@router.post("/v1/ocr")
async def process_image(payload: OcrRequestPayload) -> dict[str, object]:
    log.debug(
        "Received OCR request | model=%s | document_type=%s",
        payload.model,
        payload.document.type,
    )
    image_path = resolve_document_path(payload.document)
    try:
        response = ocr_image_path(image_path)
        pages = response.get("pages", [])
        first_page = pages[0] if pages else {}
        log.debug(
            "OCR response ready | path=%s | pages=%s | text_len=%s",
            image_path,
            len(pages),
            len(str(first_page.get("markdown", "") or "")),
        )
        return response
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        log.debug("Cleaning OCR temp image | path=%s", image_path)
        image_path.unlink(missing_ok=True)
