"""Cấu hình logging thống nhất cho API (uvicorn) và Celery worker, đọc LOG_LEVEL từ Settings."""

import logging

from app.core.config import get_settings

_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
_NOISY_LOGGERS = ("httpx", "httpcore", "sentence_transformers", "urllib3")


def setup_logging() -> None:
    level_name = get_settings().log_level.upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format=_FORMAT, datefmt="%H:%M:%S", force=True)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(max(level, logging.WARNING))
