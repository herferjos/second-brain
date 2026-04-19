from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    resolved_level = _resolve_level(level)
    logging.basicConfig(
        level=resolved_level,
        format="[%(levelname)s] [%(processName)s:%(threadName)s] [%(name)s] %(message)s",
        force=True,
    )


def get_logger(*parts: str) -> logging.Logger:
    logger = logging.getLogger("exocort")
    if not parts:
        return logger
    return logger.getChild(".".join(parts))


def _resolve_level(level: str) -> int:
    normalized = str(level).strip().upper()
    mapping = logging.getLevelNamesMapping()
    if normalized not in mapping:
        raise ValueError(f"Unsupported log level: {level}")
    return mapping[normalized]
