import logging
import os
from logging.handlers import RotatingFileHandler
from .config import settings


def configure_logging() -> None:
    os.makedirs(settings.logs_dir, exist_ok=True)
    log_path = os.path.join(settings.logs_dir, "app.log")

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    root.addHandler(ch)

    # Rotating file handler
    fh = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5)
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    root.addHandler(fh)

