"""Logging: console + rotating file under the app data directory."""

from __future__ import annotations

import logging
import logging.config

from .paths import logs_dir

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once per process (console + rotating file)."""
    logfile = logs_dir() / "finsight.log"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"std": {"format": _FORMAT, "datefmt": "%Y-%m-%d %H:%M:%S"}},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "std",
                    "stream": "ext://sys.stderr",
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "std",
                    "filename": str(logfile),
                    "maxBytes": 2_000_000,
                    "backupCount": 5,
                    "encoding": "utf-8",
                },
            },
            "root": {"level": level.upper(), "handlers": ["console", "file"]},
        }
    )
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
