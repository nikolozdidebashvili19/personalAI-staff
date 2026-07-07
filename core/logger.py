"""Shared logging — everything goes to logs/assistant.log and the console."""

import logging
from logging.handlers import RotatingFileHandler

from config.settings import LOG_DIR

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        LOG_DIR / "assistant.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(console)
    return logger
