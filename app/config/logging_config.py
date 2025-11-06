import logging
from pathlib import Path

BASE_LOGGER_NAME = "gritfeat"
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Configure a base logger that writes to logs/app.log.
    Subsequent calls are no-ops so it is safe to invoke at import time.
    """
    logger = logging.getLogger(BASE_LOGGER_NAME)
    if logger.handlers:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Prevent duplicate propagation to the root logger (uvicorn already handles console logging).
    logger.propagate = False
    return logger


def get_logger(name: str = "app") -> logging.Logger:
    """
    Retrieve a child logger under the gritfeat namespace.
    """
    return logging.getLogger(f"{BASE_LOGGER_NAME}.{name}")
