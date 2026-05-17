"""Logging compatibility - uses structlog if available, falls back to stdlib logging.

The wrapper supports both structlog-style (logger.info("msg", key=val)) and
stdlib-style (logger.info("msg %s", val)) calling conventions.
"""

import logging
import sys


class _FallbackLogger:
    """Logger wrapper that supports structlog-style keyword arguments
    by converting them to string interpolation when falling back to stdlib."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _format(self, msg: str, *args, **kwargs) -> str:
        if kwargs:
            parts = [msg]
            for k, v in kwargs.items():
                parts.append(f"{k}={v}")
            return " ".join(parts)
        return msg

    def debug(self, msg: str, *args, **kwargs):
        self._logger.debug(self._format(msg, *args, **kwargs))

    def info(self, msg: str, *args, **kwargs):
        self._logger.info(self._format(msg, *args, **kwargs))

    def warning(self, msg: str, *args, **kwargs):
        self._logger.warning(self._format(msg, *args, **kwargs))

    def error(self, msg: str, *args, **kwargs):
        self._logger.error(self._format(msg, *args, **kwargs))

    def exception(self, msg: str, *args, **kwargs):
        self._logger.exception(self._format(msg, *args, **kwargs))


def get_logger(name: str | None = None):
    """Get a logger that works with both structlog and stdlib conventions."""
    try:
        import structlog
        return structlog.get_logger(name or __name__)
    except ImportError:
        logger = logging.getLogger(name or __name__)
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return _FallbackLogger(logger)
