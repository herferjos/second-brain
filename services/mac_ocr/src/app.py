import base64
import binascii
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import HOST, PORT
from .ocr import ocr_image_path


app = FastAPI(title="Mac OCR", version="0.1.0")


class OcrDocumentPayload(BaseModel):
    type: Literal["image_url"]
    image_url: str


class OcrRequestPayload(BaseModel):
    model: str | None = None
    document: OcrDocumentPayload


@app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True}


def _resolve_document_path(document: OcrDocumentPayload) -> Path:
    image_url = document.image_url
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

    temp_file = NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        temp_file.write(image_bytes)
    finally:
        temp_file.close()

    return Path(temp_file.name)


@app.post("/v1/ocr")
async def process_image(payload: OcrRequestPayload) -> dict[str, object]:
    image_path = _resolve_document_path(payload.document)
    try:
        return ocr_image_path(image_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        image_path.unlink(missing_ok=True)


def main() -> None:
    import uvicorn
    uvicorn.run("src.app:app", host=HOST, port=PORT, reload=True)
