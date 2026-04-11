from __future__ import annotations

from pathlib import Path

import pytest

from common.models.ocr import OcrResponse
import src.ocr.vision as ocr_vision
from src.ocr.service import ocr_image_path


pytestmark = [pytest.mark.service, pytest.mark.unit, pytest.mark.ocr]


def test_ocr_image_path_returns_mistral_style_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "frame.png"
    image_path.write_bytes(b"fake-image")

    monkeypatch.setattr("src.ocr.service._recognize_texts_from_path", lambda path: ["hello world"])

    payload = ocr_image_path(image_path)

    assert isinstance(payload, OcrResponse)
    assert payload.pages[0].markdown == "hello world"
    assert payload.usage_info.pages_processed == 1
    assert payload.object == "ocr"


def test_ocr_image_path_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "missing.png"

    with pytest.raises(FileNotFoundError):
        ocr_image_path(missing)


def test_recognize_texts_extracts_text_without_bounding_box(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCandidate:
        confidence = 0.93

        def string(self) -> str:
            return "hello world"

    class FakeResult:
        def topCandidates_(self, count: int) -> list[FakeCandidate]:
            return [FakeCandidate()]

    class FakeRequest:
        @classmethod
        def alloc(cls) -> "FakeRequest":
            return cls()

        def initWithCompletionHandler_(self, callback):
            self.callback = callback
            return self

        def setRecognitionLevel_(self, value) -> None:
            pass

        def setUsesLanguageCorrection_(self, value) -> None:
            pass

        def setAutomaticallyDetectsLanguage_(self, value) -> None:
            pass

    class FakeHandler:
        def performRequests_error_(self, requests, error):
            class FakeRequestResult:
                def results(self):
                    return [FakeResult()]

            requests[0].callback(FakeRequestResult(), None)

    monkeypatch.setattr(ocr_vision.Vision, "VNRecognizeTextRequest", FakeRequest)
    monkeypatch.setattr(
        ocr_vision.Vision,
        "VNRequestTextRecognitionLevelAccurate",
        object(),
    )

    texts = ocr_vision._recognize_texts(FakeHandler())

    assert texts == ["hello world"]


def test_recognize_texts_ignores_non_numeric_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConfidence:
        def __call__(self) -> float:
            return 0.87

    class FakeCandidate:
        confidence = FakeConfidence()

        def string(self) -> str:
            return "hello world"

    class FakeResult:
        def topCandidates_(self, count: int) -> list[FakeCandidate]:
            return [FakeCandidate()]

    class FakeRequest:
        @classmethod
        def alloc(cls) -> "FakeRequest":
            return cls()

        def initWithCompletionHandler_(self, callback):
            self.callback = callback
            return self

        def setRecognitionLevel_(self, value) -> None:
            pass

        def setUsesLanguageCorrection_(self, value) -> None:
            pass

        def setAutomaticallyDetectsLanguage_(self, value) -> None:
            pass

    class FakeHandler:
        def performRequests_error_(self, requests, error):
            class FakeRequestResult:
                def results(self):
                    return [FakeResult()]

            requests[0].callback(FakeRequestResult(), None)

    monkeypatch.setattr(ocr_vision.Vision, "VNRecognizeTextRequest", FakeRequest)
    monkeypatch.setattr(
        ocr_vision.Vision,
        "VNRequestTextRecognitionLevelAccurate",
        object(),
    )

    texts = ocr_vision._recognize_texts(FakeHandler())

    assert texts == ["hello world"]
