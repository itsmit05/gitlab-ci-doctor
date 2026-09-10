"""Rotating file logging. Captures both logging calls and plain print()
output into config.LOG_FILE, so the detached (hidden) service has a full
audit trail of scans, detections, and email sends."""

import logging
import sys
from logging.handlers import RotatingFileHandler

import config


class _StreamToLog:
    """File-like object that forwards writes (e.g. print()) into a logger."""

    def __init__(self, logger, level):
        self._logger = logger
        self._level = level
        self._buf = ""

    def write(self, msg):
        self._buf += msg
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._logger.log(self._level, line)

    def flush(self):
        if self._buf.strip():
            self._logger.log(self._level, self._buf.strip())
        self._buf = ""


def setup():
    fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    file_handler = RotatingFileHandler(
        config.LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    # Created BEFORE we redirect streams, so it keeps the real console stream
    # (avoids a feedback loop). Harmless when the service runs hidden.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Send any remaining print()/traceback output to the log file too.
    sys.stdout = _StreamToLog(logging.getLogger("stdout"), logging.INFO)
    sys.stderr = _StreamToLog(logging.getLogger("stderr"), logging.ERROR)

    logging.getLogger("startup").info("Logging initialized -> %s", config.LOG_FILE)
