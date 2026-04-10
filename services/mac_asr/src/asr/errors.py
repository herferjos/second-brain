from __future__ import annotations


def _is_no_speech_error(error_message: str) -> bool:
    msg = (error_message or "").lower()
    if "no speech detected" in msg:
        return True
    if "kafassistanterrordomain" not in msg:
        return False
    if "code=1110" in msg:
        return True
    if "code=203" in msg and "retry" in msg:
        return True
    return "sirispeecherrordomain" in msg and "code=1" in msg and "retry" in msg
