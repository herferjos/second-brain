from __future__ import annotations

from fastapi import APIRouter, HTTPException

from common.models.ocr import OcrRequestPayload, OcrResponse
from common.utils.logs import get_logger
from src.document.resolver import resolve_document_path
from src.ocr.service import ocr_image_path

router = APIRouter()
log = get_logger("mac_ocr", "api")


@router.post("/v1/ocr", response_model=OcrResponse)
async def process_image(payload: OcrRequestPayload) -> OcrResponse:
    log.debug(
        "Received OCR request | model=%s | document_type=%s",
        payload.model,
        payload.document.type,
    )
    image_path = resolve_document_path(payload.document)
    try:
        response = ocr_image_path(image_path)
        log.debug(
            "OCR response ready | path=%s | pages=%s | text_len=%s",
            image_path,
            len(response.pages),
            len(response.pages[0].markdown) if response.pages else 0,
        )
        return response
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        log.debug("Cleaning OCR temp image | path=%s", image_path)
        image_path.unlink(missing_ok=True)
