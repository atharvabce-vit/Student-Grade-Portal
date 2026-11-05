"""Application logging setup.

Logs go to the console and to a rotating file so the app keeps a history
without the log file growing forever.
"""

import logging
from logging.handlers import RotatingFileHandler

from config import LOG_FILE, LOG_LEVEL

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def configure_logging():
    """Configure the root logger once and return it."""
    root = logging.getLogger()
    if root.handlers:
        return root

    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FORMAT))

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))

    root.addHandler(console)
    root.addHandler(file_handler)
    return root
