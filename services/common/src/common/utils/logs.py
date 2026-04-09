from __future__ import annotations

import logging


def get_logger(*parts: str) -> logging.Logger:
    logger = logging.getLogger("uvicorn.error")
    if not parts:
        return logger
    return logger.getChild(".".join(parts))


__all__ = ["get_logger"]
