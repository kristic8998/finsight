"""Automation Center: job registry, scheduler, folder watcher, email.

Jobs are named callables registered by other modules ("generate daily
MIS", "backup app data", ...). The scheduler thread fires them on
interval or daily-at-time triggers; the folder watcher fires a job when
a matching file lands in a watched directory (classic use: auto-recon
when the bank statement arrives). Every run is logged to the app DB
with status and detail — auditable automation, not magic.
"""

from __future__ import annotations

import contextlib
import fnmatch
import logging
import smtplib
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from ..core import credentials
from ..core.appdb import AppDB
from ..core.config import EmailConfig
from ..core.tasks import retry

logger = logging.getLogger(__name__)

JobFunc = Callable[[], str]  # returns a human-readable result line


@dataclass
class Schedule:
    """When a job should run: every N minutes, or daily at HH:MM."""

    job: str
    every_minutes: int | None = None
    daily_at: str | None = None  # "07:30"
    enabled: bool = True
    last_run: datetime | None = None

    def next_due(self, now: datetime) -> datetime:
        if self.every_minutes:
            base = self.last_run or (now - timedelta(minutes=self.every_minutes))
            return base + timedelta(minutes=self.every_minutes)
        if self.daily_at:
            hour, minute = (int(x) for x in self.daily_at.split(":"))
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if self.last_run and self.last_run >= candidate:
                candidate += timedelta(days=1)
            elif candidate < now and (self.last_run is None or self.last_run < candidate):
                return candidate  # missed today's slot → run now
            return candidate
        return now + timedelta(days=3650)  # effectively never


@dataclass
class Watch:
    """Folder watcher rule: when a file matching pattern appears, run job."""

    folder: str
    pattern: str
    job: str
    enabled: bool = True
    seen: set[str] = field(default_factory=set)


class AutomationCenter:
    """Owns registered jobs, schedules, watches, and the runner thread."""

    def __init__(self, appdb: AppDB, poll_seconds: int = 20) -> None:
        self._appdb = appdb
        self._poll = max(5, poll_seconds)
        self._jobs: dict[str, JobFunc] = {}
        self._schedules: list[Schedule] = []
        self._watches: list[Watch] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- registration ----------------------------------------------------
    def register_job(self, name: str, func: JobFunc) -> None:
        self._jobs[name] = func

    def job_names(self) -> list[str]:
        return sorted(self._jobs)

    def add_schedule(self, schedule: Schedule) -> None:
        if schedule.job not in self._jobs:
            raise ValueError(f"unknown job: {schedule.job}")
        if not schedule.every_minutes and not schedule.daily_at:
            raise ValueError("schedule needs every_minutes or daily_at")
        with self._lock:
            self._schedules.append(schedule)

    def schedules(self) -> list[Schedule]:
        with self._lock:
            return list(self._schedules)

    def remove_schedule(self, index: int) -> None:
        with self._lock:
            if 0 <= index < len(self._schedules):
                self._schedules.pop(index)

    def add_watch(self, watch: Watch) -> None:
        if watch.job not in self._jobs:
            raise ValueError(f"unknown job: {watch.job}")
        folder = Path(watch.folder)
        if not folder.is_dir():
            raise ValueError(f"watch folder does not exist: {folder}")
        watch.seen = {p.name for p in folder.iterdir() if p.is_file()}
        with self._lock:
            self._watches.append(watch)

    def watches(self) -> list[Watch]:
        with self._lock:
            return list(self._watches)

    # ---- execution ---------------------------------------------------------
    def run_job(self, name: str) -> str:
        """Run one job now (used by the UI 'Run' button and the scheduler)."""
        func = self._jobs.get(name)
        if func is None:
            raise ValueError(f"unknown job: {name}")
        run_id = self._appdb.job_started(name)
        try:
            detail = func()
            self._appdb.job_finished(run_id, "success", detail)
            logger.info("job '%s' succeeded: %s", name, detail)
            return detail
        except Exception as exc:
            self._appdb.job_finished(run_id, "failed", str(exc))
            logger.error("job '%s' failed: %s", name, exc)
            raise

    def _tick(self, now: datetime) -> None:
        with self._lock:
            due = [s for s in self._schedules if s.enabled and s.next_due(now) <= now]
        for schedule in due:
            schedule.last_run = now
            with contextlib.suppress(Exception):  # logged in run_job; loop survives
                self.run_job(schedule.job)

        with self._lock:
            watches = [w for w in self._watches if w.enabled]
        for watch in watches:
            folder = Path(watch.folder)
            if not folder.is_dir():
                continue
            current = {p.name for p in folder.iterdir() if p.is_file()}
            new_files = [
                n for n in current - watch.seen if fnmatch.fnmatch(n.lower(), watch.pattern.lower())
            ]
            watch.seen = current
            for filename in new_files:
                logger.info("watcher: %s matched %s → job '%s'", filename, watch.pattern, watch.job)
                with contextlib.suppress(Exception):  # logged in run_job
                    self.run_job(watch.job)

    def _loop(self) -> None:
        while not self._stop.wait(self._poll):
            try:
                self._tick(datetime.now())
            except Exception as exc:  # never let the loop die
                logger.error("automation tick failed: %s", exc)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="finsight-automation", daemon=True)
        self._thread.start()
        logger.info("automation loop started (poll %ss)", self._poll)

    def stop(self) -> None:
        self._stop.set()
        logger.info("automation loop stopping")


@retry((smtplib.SMTPException, OSError), attempts=3, delay=1.0)
def send_email(
    config: EmailConfig,
    to: list[str],
    subject: str,
    body: str,
    attachments: list[Path] | None = None,
) -> str:
    """Send a report email using vault-stored credentials (retried)."""
    if not config.smtp_host or not config.sender:
        raise ValueError("email is not configured (SMTP host/sender missing)")
    message = EmailMessage()
    message["From"] = config.sender
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message.set_content(body)
    for attachment in attachments or []:
        data = Path(attachment).read_bytes()
        message.add_attachment(
            data,
            maintype="application",
            subtype="octet-stream",
            filename=Path(attachment).name,
        )
    password = credentials.get_secret("smtp_password")
    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20) as smtp:
        if config.use_tls:
            smtp.starttls()
        if password:
            smtp.login(config.sender, password)
        smtp.send_message(message)
    return f"sent '{subject}' to {len(to)} recipient(s)"
