"""Auto-backup: zip the app data folder, keep the newest N archives."""

from __future__ import annotations

import logging
import zipfile
from datetime import datetime
from pathlib import Path

from .paths import app_data_dir, backups_dir

logger = logging.getLogger(__name__)

_SKIP_DIRS = {"backups", "logs"}


def create_backup(keep: int = 10) -> Path:
    """Zip settings + databases + reports into a timestamped archive.

    Returns the archive path. Oldest archives beyond ``keep`` are pruned.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    archive = backups_dir() / f"finsight-backup-{stamp}.zip"
    counter = 1
    while archive.exists():  # guarantee uniqueness even for back-to-back backups
        archive = backups_dir() / f"finsight-backup-{stamp}-{counter}.zip"
        counter += 1
    root = app_data_dir()

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if relative.parts and relative.parts[0] in _SKIP_DIRS:
                continue
            if path.suffix in {".tmp", ".zip"}:
                continue
            zf.write(path, relative.as_posix())

    archives = sorted(
        backups_dir().glob("finsight-backup-*.zip"), key=lambda p: p.stat().st_mtime_ns
    )
    for old in archives[:-keep] if keep > 0 else []:
        old.unlink(missing_ok=True)
        logger.info("pruned old backup %s", old.name)

    logger.info("backup written: %s", archive.name)
    return archive


def list_backups() -> list[Path]:
    """Newest first, ordered by actual creation time."""
    return sorted(
        backups_dir().glob("finsight-backup-*.zip"),
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True,
    )
