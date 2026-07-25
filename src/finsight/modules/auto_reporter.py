"""Visual Auto-Reporter — scheduling made to feel like an alarm clock.

Pure logic + a small daemon thread, no UI. A :class:`ReportJob` says
*which* report (a one-click template or a saved Visual Builder report),
*from which* source file, and *when* (daily / weekly / monthly at
HH:MM). Jobs persist to JSON, so they survive restarts; the loop checks
every ~20 seconds and fires anything due.

Honest scope: like every FinSight automation, jobs run **while the app
is open** — this is a desktop tool, not a server.

The firing logic lives in :func:`AutoReporter.run_due_jobs` (pure,
deterministic, unit-tested); the thread merely calls it on a timer.
"""

from __future__ import annotations

import calendar
import json
import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from ..core.paths import app_data_dir, reports_dir

logger = logging.getLogger(__name__)

FREQUENCIES = ("Daily", "Weekly", "Monthly")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass
class ReportJob:
    name: str
    kind: str  # "template:<key>" or "builder:<saved report name>"
    source_path: str
    frequency: str  # Daily | Weekly | Monthly
    at: str  # "HH:MM"
    weekday: int = 0  # 0=Monday, used when Weekly
    monthday: int = 1  # 1..28, used when Monthly
    enabled: bool = True
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    last_run: str = ""
    last_output: str = ""
    next_run: str = ""

    def schedule_text(self) -> str:
        if self.frequency == "Weekly":
            return f"Weekly · {WEEKDAYS[self.weekday]} {self.at}"
        if self.frequency == "Monthly":
            return f"Monthly · day {self.monthday} at {self.at}"
        return f"Daily · {self.at}"


def compute_next_run(job: ReportJob, now: datetime) -> datetime:
    """The next moment this job should fire, strictly after ``now``."""
    hour, minute = (int(part) for part in job.at.split(":"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if job.frequency == "Daily":
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    if job.frequency == "Weekly":
        ahead = (job.weekday - candidate.weekday()) % 7
        candidate += timedelta(days=ahead)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate
    if job.frequency == "Monthly":
        day = min(job.monthday, calendar.monthrange(now.year, now.month)[1])
        candidate = candidate.replace(day=day)
        if candidate <= now:
            year = now.year + (1 if now.month == 12 else 0)
            month = 1 if now.month == 12 else now.month + 1
            day = min(job.monthday, calendar.monthrange(year, month)[1])
            candidate = candidate.replace(year=year, month=month, day=day)
        return candidate
    raise ValueError(f"unknown frequency: {job.frequency}")


def _generate(job: ReportJob, output_dir: Path) -> Path:
    """Read the source file and produce the report — the actual work."""
    from .excel_tools import read_table
    from .mis_builder import build_pivot, export_pivot, get_report
    from .mis_templates import export_template, run_template

    frame = read_table(job.source_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in job.name) or "report"
    out = output_dir / f"{safe}_{stamp}.xlsx"

    scheme, _, target = job.kind.partition(":")
    if scheme == "template":
        return export_template(run_template(target, frame), out)
    if scheme == "builder":
        saved = get_report(target)
        if saved is None:
            raise ValueError(f"saved report '{target}' no longer exists")
        return export_pivot(build_pivot(frame, saved.config), out)
    raise ValueError(f"unknown job kind: {job.kind}")


class AutoReporter:
    """Persisted job store + background firing loop."""

    def __init__(
        self,
        store_path: Path | None = None,
        output_dir: Path | None = None,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self._store = store_path if store_path is not None else app_data_dir() / "auto_reports.json"
        self._output_dir = output_dir if output_dir is not None else reports_dir()
        self._on_event = on_event or (lambda line: None)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._jobs: list[ReportJob] = self._load()

    # ---- persistence -------------------------------------------------------
    def _load(self) -> list[ReportJob]:
        if not self._store.is_file():
            return []
        try:
            raw = json.loads(self._store.read_text(encoding="utf-8"))
            return [ReportJob(**item) for item in raw]
        except Exception as exc:  # noqa: BLE001 - a bad store must never block startup
            logger.warning("ignoring unreadable auto-report store: %s", exc)
            return []

    def _save(self) -> None:
        self._store.write_text(
            json.dumps([asdict(job) for job in self._jobs], indent=2), encoding="utf-8"
        )

    # ---- job management ------------------------------------------------------
    def jobs(self) -> list[ReportJob]:
        with self._lock:
            return list(self._jobs)

    def add_job(self, job: ReportJob, now: datetime | None = None) -> ReportJob:
        job.next_run = compute_next_run(job, now or datetime.now()).isoformat(timespec="minutes")
        with self._lock:
            self._jobs = [j for j in self._jobs if j.job_id != job.job_id]
            self._jobs.append(job)
            self._save()
        self._on_event(f"ACTIVATED  {job.name} — {job.schedule_text()} (next: {job.next_run})")
        return job

    def remove_job(self, job_id: str) -> None:
        with self._lock:
            self._jobs = [j for j in self._jobs if j.job_id != job_id]
            self._save()

    def set_enabled(self, job_id: str, enabled: bool) -> None:
        with self._lock:
            for job in self._jobs:
                if job.job_id == job_id:
                    job.enabled = enabled
                    if enabled:
                        job.next_run = compute_next_run(job, datetime.now()).isoformat(
                            timespec="minutes"
                        )
            self._save()

    # ---- firing ------------------------------------------------------------------
    def run_job_now(self, job_id: str) -> Path:
        """Fire one job immediately (used by the 'Run now' button)."""
        with self._lock:
            job = next((j for j in self._jobs if j.job_id == job_id), None)
        if job is None:
            raise ValueError("job not found")
        return self._fire(job, reschedule_from=datetime.now())

    def run_due_jobs(self, now: datetime | None = None) -> list[Path]:
        """Fire every enabled job whose next_run has passed. Deterministic; tested."""
        moment = now or datetime.now()
        outputs: list[Path] = []
        with self._lock:
            due = [
                job
                for job in self._jobs
                if job.enabled and job.next_run and datetime.fromisoformat(job.next_run) <= moment
            ]
        for job in due:
            try:
                outputs.append(self._fire(job, reschedule_from=moment))
            except Exception as exc:  # noqa: BLE001 - one bad job must not stop the loop
                logger.error("auto-report %s failed: %s", job.name, exc)
                self._on_event(f"FAILED     {job.name} — {exc}")
                with self._lock:
                    job.next_run = compute_next_run(job, moment).isoformat(timespec="minutes")
                    self._save()
        return outputs

    def _fire(self, job: ReportJob, reschedule_from: datetime) -> Path:
        output = _generate(job, self._output_dir)
        with self._lock:
            job.last_run = reschedule_from.isoformat(timespec="minutes")
            job.last_output = str(output)
            job.next_run = compute_next_run(job, reschedule_from).isoformat(timespec="minutes")
            self._save()
        self._on_event(f"GENERATED  {job.name} → {output.name} (next: {job.next_run})")
        return output

    # ---- lifecycle -------------------------------------------------------------------
    def start(self, poll_seconds: float = 20.0) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()

        def loop() -> None:
            while not self._stop.wait(poll_seconds):
                try:
                    self.run_due_jobs()
                except Exception as exc:  # noqa: BLE001 - the loop must never die
                    logger.error("auto-reporter loop error: %s", exc)

        self._thread = threading.Thread(target=loop, name="finsight-autoreport", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
