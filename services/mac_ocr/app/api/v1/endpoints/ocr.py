from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.document import OcrRequestPayload, resolve_document_path
from src.ocr import ocr_image_path

router = APIRouter()


@router.post("/v1/ocr")
async def process_image(payload: OcrRequestPayload) -> dict[str, object]:
    image_path = resolve_document_path(payload.document)
    try:
        return ocr_image_path(image_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        image_path.unlink(missing_ok=True)
