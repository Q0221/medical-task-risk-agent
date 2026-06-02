"""日志配置：基于标准 logging，输出到 stdout。"""

import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    level = logging.DEBUG if settings.DEBUG else logging.INFO

    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root.setLevel(level)
    root.addHandler(handler)

    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
