import logging
import os
import sys
from datetime import datetime

LOG_ROOT = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_ROOT, exist_ok=True)

LOG_FORMAT = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def get_logger(name: str = "data_analysis_agent") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(LOG_FORMAT)
    logger.addHandler(console)

    log_file = os.path.join(LOG_ROOT, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(LOG_FORMAT)
    logger.addHandler(file_handler)

    return logger


logger = get_logger()
