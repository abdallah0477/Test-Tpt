"""Structured JSON log lines on stdout, with job_id/session_id when known.

Page content and secrets are never logged: only ids, statuses and messages.
"""

import json
import logging
import sys

EXTRA_KEYS = ("job_id", "session_id", "status")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {"level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        line |= {key: getattr(record, key) for key in EXTRA_KEYS if hasattr(record, key)}
        if record.exc_info:
            line["error"] = f"{record.exc_info[0].__name__}: {record.exc_info[1]}"[:500]
        return json.dumps(line)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("runner")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
