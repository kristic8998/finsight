"""Tests for the Visual Auto-Reporter scheduler."""

from __future__ import annotations

from datetime import datetime

import pytest

from finsight.modules.auto_reporter import (
    AutoReporter,
    ReportJob,
    compute_next_run,
)
from finsight.modules.mis_builder import BuilderConfig, SavedReport, save_report
from finsight.modules.mis_samples import sample_lending_dataset


def _job(**overrides) -> ReportJob:
    base = {
        "name": "Test",
        "kind": "template:portfolio_health",
        "source_path": "",
        "frequency": "Daily",
        "at": "09:00",
    }
    base.update(overrides)
    return ReportJob(**base)


class TestNextRun:
    def test_daily_before_and_after_time(self):
        job = _job(at="09:00")
        before = compute_next_run(job, datetime(2026, 7, 25, 8, 0))
        after = compute_next_run(job, datetime(2026, 7, 25, 10, 0))
        assert before == datetime(2026, 7, 25, 9, 0)
        assert after == datetime(2026, 7, 26, 9, 0)

    def test_weekly_targets_weekday(self):
        job = _job(frequency="Weekly", weekday=0, at="07:30")  # Monday
        # 2026-07-25 is a Saturday → next Monday is the 27th.
        assert compute_next_run(job, datetime(2026, 7, 25, 12, 0)) == datetime(2026, 7, 27, 7, 30)
        # On Monday after the time → the following Monday.
        assert compute_next_run(job, datetime(2026, 7, 27, 8, 0)) == datetime(2026, 8, 3, 7, 30)

    def test_monthly_clamps_short_months(self):
        job = _job(frequency="Monthly", monthday=31, at="09:00")
        assert compute_next_run(job, datetime(2026, 2, 10, 8, 0)) == datetime(2026, 2, 28, 9, 0)

    def test_monthly_rolls_over_year(self):
        job = _job(frequency="Monthly", monthday=5, at="09:00")
        assert compute_next_run(job, datetime(2026, 12, 6, 10, 0)) == datetime(2027, 1, 5, 9, 0)

    def test_unknown_frequency_rejected(self):
        with pytest.raises(ValueError, match="frequency"):
            compute_next_run(_job(frequency="Hourly"), datetime(2026, 1, 1))


class TestReporter:
    def _reporter(self, tmp_path, **kwargs) -> AutoReporter:
        return AutoReporter(store_path=tmp_path / "jobs.json", output_dir=tmp_path, **kwargs)

    def _source(self, tmp_path) -> str:
        path = tmp_path / "book.csv"
        sample_lending_dataset(80).to_csv(path, index=False)
        return str(path)

    def test_jobs_persist_across_instances(self, tmp_path):
        reporter = self._reporter(tmp_path)
        reporter.add_job(_job(source_path=self._source(tmp_path)))
        reborn = self._reporter(tmp_path)
        assert len(reborn.jobs()) == 1
        assert reborn.jobs()[0].next_run  # schedule survived

    def test_due_job_fires_and_reschedules(self, tmp_path):
        events: list[str] = []
        reporter = self._reporter(tmp_path, on_event=events.append)
        job = reporter.add_job(
            _job(source_path=self._source(tmp_path), at="23:00"),
            now=datetime(2026, 7, 25, 10, 0),
        )
        outputs = reporter.run_due_jobs(now=datetime(2026, 7, 26, 1, 0))
        assert len(outputs) == 1 and outputs[0].is_file()
        refreshed = reporter.jobs()[0]
        assert refreshed.last_run and refreshed.next_run == "2026-07-26T23:00"
        assert any(line.startswith("GENERATED") for line in events)
        assert job.job_id == refreshed.job_id

    def test_not_due_does_nothing(self, tmp_path):
        reporter = self._reporter(tmp_path)
        reporter.add_job(
            _job(source_path=self._source(tmp_path), at="23:00"),
            now=datetime(2026, 7, 25, 10, 0),
        )
        assert reporter.run_due_jobs(now=datetime(2026, 7, 25, 12, 0)) == []

    def test_disabled_job_never_fires(self, tmp_path):
        reporter = self._reporter(tmp_path)
        job = reporter.add_job(
            _job(source_path=self._source(tmp_path)), now=datetime(2026, 7, 25, 8, 0)
        )
        reporter.set_enabled(job.job_id, False)
        assert reporter.run_due_jobs(now=datetime(2030, 1, 1)) == []

    def test_builder_kind_uses_saved_recipe(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FINSIGHT_HOME", str(tmp_path))  # saved-recipe store location
        source = self._source(tmp_path)
        save_report(
            SavedReport("Branch Sum", source, BuilderConfig("branch", "loan_amount", "Sum"))
        )
        reporter = self._reporter(tmp_path)
        reporter.add_job(
            _job(kind="builder:Branch Sum", source_path=source, at="06:00"),
            now=datetime(2026, 7, 25, 5, 0),
        )
        outputs = reporter.run_due_jobs(now=datetime(2026, 7, 25, 6, 5))
        assert len(outputs) == 1 and outputs[0].is_file()

    def test_failed_job_logs_and_reschedules(self, tmp_path):
        events: list[str] = []
        reporter = self._reporter(tmp_path, on_event=events.append)
        reporter.add_job(
            _job(source_path=str(tmp_path / "missing.csv"), at="06:00"),
            now=datetime(2026, 7, 25, 5, 0),
        )
        outputs = reporter.run_due_jobs(now=datetime(2026, 7, 25, 6, 5))
        assert outputs == []
        assert any(line.startswith("FAILED") for line in events)
        assert reporter.jobs()[0].next_run == "2026-07-26T06:00"  # rescheduled, not stuck

    def test_run_now_and_remove(self, tmp_path):
        reporter = self._reporter(tmp_path)
        job = reporter.add_job(_job(source_path=self._source(tmp_path)))
        output = reporter.run_job_now(job.job_id)
        assert output.is_file()
        reporter.remove_job(job.job_id)
        assert reporter.jobs() == []
