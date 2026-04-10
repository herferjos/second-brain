from __future__ import annotations

from pathlib import Path

import Vision
import objc

from common.utils.logs import get_logger

log = get_logger("mac_ocr", "ocr")


def _recognize_texts_from_path(path: Path) -> list[str]:
    log.debug("Creating Vision handler | path=%s | size_bytes=%s", path, path.stat().st_size)
    image_url = objc.lookUpClass("NSURL").fileURLWithPath_(str(path))
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(image_url, {})
    return _recognize_texts(handler)


def _recognize_texts(handler) -> list[str]:
    texts: list[str] = []

    def callback(request, error) -> None:
        if error is not None:
            log.debug("Vision callback returned error | error=%s", error)
            raise RuntimeError(str(error))
        results = getattr(request, "results", None)
        if callable(results):
            results = results()
        if results is None:
            results = []
        log.debug("Vision callback results | result_count=%s", len(results))
        for result in results:
            candidates = getattr(result, "topCandidates_", None)
            if candidates is not None:
                candidates = candidates(1)
            if not candidates:
                log.debug("Skipping Vision result with no candidates")
                continue
            candidate = candidates[0]
            text = str(candidate.string() or "").strip()
            if not text:
                log.debug("Skipping Vision candidate with empty text")
                continue
            confidence = _coerce_confidence(getattr(candidate, "confidence", 0.0))
            log.debug("Accepted OCR text | text=%r | confidence=%.4f", text, confidence)
            texts.append(text)

    request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(callback)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    if hasattr(request, "setAutomaticallyDetectsLanguage_"):
        request.setAutomaticallyDetectsLanguage_(True)
    log.debug("Submitting Vision request")
    handler.performRequests_error_([request], None)
    log.debug("Vision request completed | accepted_text_count=%s", len(texts))
    return texts


def _coerce_confidence(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        if callable(value):
            try:
                return float(value())
            except (TypeError, ValueError):
                return 0.0
        return 0.0
