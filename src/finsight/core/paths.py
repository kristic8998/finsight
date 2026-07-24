"""Application data locations.

All user data (settings DB, demo database, logs, backups, generated
reports) lives under one per-user folder so backup/restore is trivial:
``%LOCALAPPDATA%/FinSight`` on Windows, ``~/.finsight`` elsewhere.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    """Per-user writable data directory (created on first call)."""
    override = os.environ.get("FINSIGHT_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FinSight"
    else:
        base = Path.home() / ".finsight"
    base.mkdir(parents=True, exist_ok=True)
    return base


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(exist_ok=True)
    return path


def reports_dir() -> Path:
    path = app_data_dir() / "reports"
    path.mkdir(exist_ok=True)
    return path


def backups_dir() -> Path:
    path = app_data_dir() / "backups"
    path.mkdir(exist_ok=True)
    return path


def appdb_path() -> Path:
    return app_data_dir() / "finsight.db"


def demo_db_path() -> Path:
    return app_data_dir() / "demo_lending.db"
