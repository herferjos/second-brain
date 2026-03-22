from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import objc


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    x: float
    y: float
    width: float
    height: float


def _vision():
    import Vision

    return Vision


def ocr_image_path(path: Path) -> dict[str, object]:
    image_path = path.expanduser().resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    lines = _recognize_lines_from_path(image_path)
    ordered_lines = sorted(lines, key=lambda item: (-item.y, item.x, -item.confidence))
    return {
        "text": "\n".join(item.text for item in ordered_lines),
    }


def _recognize_lines_from_path(path: Path) -> list[OcrLine]:
    image_url = objc.lookUpClass("NSURL").fileURLWithPath_(str(path))
    handler = _vision().VNImageRequestHandler.alloc().initWithURL_options_(image_url, {})
    return _recognize_lines(handler)


def _recognize_lines(handler) -> list[OcrLine]:
    Vision = _vision()
    lines: list[OcrLine] = []
    seen: set[tuple[str, int, int, int, int]] = set()

    for use_correction in (True, False):
        request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(None)
        request.setRecognitionLevel_(getattr(Vision, "VNRequestTextRecognitionLevelFast", 0))
        request.setUsesLanguageCorrection_(use_correction)
        if hasattr(request, "setAutomaticallyDetectsLanguage_"):
            request.setAutomaticallyDetectsLanguage_(True)
        if hasattr(request, "setMinimumTextHeight_"):
            request.setMinimumTextHeight_(0.0)

        success, error = handler.performRequests_error_([request], None)
        if not success:
            message = str(error) if error is not None else "unknown Vision error"
            raise RuntimeError(f"Vision OCR failed: {message}")

        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if not candidates:
                continue

            candidate = candidates[0]
            text = _clean_text(str(candidate.string() or ""))
            if not text:
                continue

            box = observation.boundingBox()
            line = OcrLine(
                text=text,
                confidence=float(candidate.confidence()),
                x=float(box.origin.x),
                y=float(box.origin.y),
                width=float(box.size.width),
                height=float(box.size.height),
            )
            key = (
                line.text,
                round(line.x * 1000),
                round(line.y * 1000),
                round(line.width * 1000),
                round(line.height * 1000),
            )
            if key in seen:
                continue
            seen.add(key)
            lines.append(line)

    return sorted(lines, key=lambda item: (-item.y, item.x, -item.confidence))


def _clean_text(text: str) -> str:
    compact = " ".join(text.replace("\n", " ").split()).strip()
    if not compact:
        return ""
    if compact in {"|", "||", "lll", "[]", "()", "{}", "..."}:
        return ""
    if len(compact) <= 2 and not any(char.isalnum() for char in compact):
        return ""
    return compact
