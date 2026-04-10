from __future__ import annotations

import threading

import Speech

from common.utils.logs import get_logger

log = get_logger("mac_asr", "asr")


def ensure_speech_permission(prompt: bool = False) -> bool:
    status = int(Speech.SFSpeechRecognizer.authorizationStatus())
    authorized = int(getattr(Speech, "SFSpeechRecognizerAuthorizationStatusAuthorized", 3))
    not_determined = int(getattr(Speech, "SFSpeechRecognizerAuthorizationStatusNotDetermined", 0))
    log.debug("Checking speech permission | status=%s | prompt=%s", status, prompt)

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
