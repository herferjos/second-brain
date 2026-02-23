import logging


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("second_brain")
    normalized_level = (level or "INFO").upper()

    if getattr(setup_logging, "_configured", False):
        logger.setLevel(normalized_level)
        return logger

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.setLevel(normalized_level)
    logger.propagate = False

    setup_logging._configured = True
    return logger
