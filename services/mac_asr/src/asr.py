from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import objc


@dataclass(frozen=True)
class Transcription:
    text: str
    locale: str

    def to_dict(self) -> dict[str, object]:
        return {"text": self.text, "locale": self.locale}


def _speech():
    import Speech
    return Speech


def _foundation():
    import Foundation
    return Foundation


def ensure_speech_permission(prompt: bool = False) -> bool:
    import threading
    Speech = _speech()
    status = int(Speech.SFSpeechRecognizer.authorizationStatus())
    authorized = int(getattr(Speech, "SFSpeechRecognizerAuthorizationStatusAuthorized", 3))
    not_determined = int(getattr(Speech, "SFSpeechRecognizerAuthorizationStatusNotDetermined", 0))

    if status == authorized:
        return True
    if status != not_determined or not prompt:
        return False

    done = threading.Event()
    granted = {"value": False}

    def handler(value) -> None:
        granted["value"] = int(value) == authorized
        done.set()

    Speech.SFSpeechRecognizer.requestAuthorization_(handler)
    done.wait(30.0)
    return bool(granted["value"])


def transcribe_audio_file(path: Path, *, locale: str, timeout_s: float) -> Transcription:
    Foundation = _foundation()
    Speech = _speech()

    recognizer = Speech.SFSpeechRecognizer.alloc().init()
    if recognizer is None:
        raise RuntimeError("Speech recognizer is not available.")

    request = Speech.SFSpeechURLRecognitionRequest.alloc().initWithURL_(
        objc.lookUpClass("NSURL").fileURLWithPath_(str(path))
    )
    if hasattr(request, "setShouldReportPartialResults_"):
        request.setShouldReportPartialResults_(False)

    state = {"text": "", "done": False, "error": ""}

    def handler(result, error) -> None:
        if result is not None:
            state["text"] = str(result.bestTranscription().formattedString() or "")
            state["done"] = True
            return
        if error is not None:
            state["error"] = str(error)
            state["done"] = True

    task = recognizer.recognitionTaskWithRequest_resultHandler_(request, handler)
    run_loop = Foundation.NSRunLoop.currentRunLoop()
    deadline = time.monotonic() + max(1.0, timeout_s)

    while not state["done"] and time.monotonic() < deadline:
        run_loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.05))

    del task

    if state["error"] and not state["text"]:
        raise RuntimeError(state["error"])

    return Transcription(text=str(state["text"]).strip(), locale=locale)
