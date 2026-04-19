from __future__ import annotations

from .models import OcrPage, OcrResponse
from ..common import coerce_mapping


def parse_ocr_response(response: object) -> OcrResponse:
    payload = coerce_mapping(response, "OCR")
    pages_value = payload.get("pages")
    if not isinstance(pages_value, list) or not pages_value:
        raise ValueError("OCR response must include a non-empty `pages` list.")

    pages: list[OcrPage] = []
    for page_value in pages_value:
        page = coerce_mapping(page_value, "OCR page")
        index = page.get("index")
        markdown = page.get("markdown")
        if not isinstance(index, int):
            raise ValueError("OCR page must include an integer `index` field.")
        if not isinstance(markdown, str):
            raise ValueError("OCR page must include a string `markdown` field.")
        markdown = markdown.strip()
        if not markdown:
            raise ValueError("OCR page markdown is empty.")
        pages.append(OcrPage(index=index, markdown=markdown))

    return OcrResponse(pages=tuple(pages))


def ocr_text(response: object) -> str:
    parsed = parse_ocr_response(response)
    return "\n".join(page.markdown for page in parsed.pages).strip()
