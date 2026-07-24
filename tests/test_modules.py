"""Module tests: recon, excel tools, NLQ, analytics, MIS, automation, productivity."""

from __future__ import annotations

import time

import pandas as pd
import pytest

from finsight.modules import excel_tools as xt
from finsight.modules.automation import AutomationCenter, Schedule, Watch
from finsight.modules.mis import MisGenerator
from finsight.modules.productivity import ProductivityService
from finsight.modules.recon import ReconError, export_recon_report, reconcile


class TestRecon:
    def _frames(self):
        ledger = pd.DataFrame(
            {
                "utr": ["T1", "T2", "T3", "T4", "T4"],
                "amount": [100.0, 200.0, 300.0, 50.0, 50.0],
            }
        )
        bank = pd.DataFrame(
            {
                "utr": ["T1", "T2", "T5"],
                "amount": [100.0, 210.0, 75.0],
            }
        )
        return ledger, bank

    def test_categories(self):
        ledger, bank = self._frames()
        result = reconcile(ledger, bank, key="utr", amount="amount")
        assert int(result.stats["matched"]) == 1  # T1
        assert int(result.stats["amount_mismatch"]) == 1  # T2
        assert int(result.stats["only_left"]) == 2  # T3, T4(agg)
        assert int(result.stats["only_right"]) == 1  # T5
        assert int(result.stats["dup_left"]) == 2  # two T4 rows
        assert "matched" in result.summary

    def test_tolerance_absorbs_small_diffs(self):
        ledger, bank = self._frames()
        result = reconcile(ledger, bank, key="utr", amount="amount", tolerance=15.0)
        assert int(result.stats["amount_mismatch"]) == 0
        assert int(result.stats["matched"]) == 2

    def test_bad_inputs(self):
        ledger, bank = self._frames()
        with pytest.raises(ReconError):
            reconcile(ledger, bank, key="missing", amount="amount")
        bad = ledger.assign(amount=["x", 1, 2, 3, 4])
        with pytest.raises(ReconError):
            reconcile(bad, bank, key="utr", amount="amount")

    def test_export_report(self, tmp_path):
        ledger, bank = self._frames()
        result = reconcile(ledger, bank, key="utr", amount="amount")
        path = export_recon_report(result, tmp_path / "recon.xlsx")
        sheets = pd.read_excel(path, sheet_name=None)
        assert "Summary" in sheets and "Amount Mismatch" in sheets
        assert "Investigation" in sheets  # root-cause sheet added in v1.2
        assert len(sheets) >= 8


class TestExcelTools:
    def test_merge_and_source_column(self, tmp_path):
        for i in range(3):
            pd.DataFrame({"a": [i], "b": [i * 2]}).to_excel(tmp_path / f"f{i}.xlsx", index=False)
        merged = xt.merge_files([tmp_path / f"f{i}.xlsx" for i in range(3)])
        assert len(merged) == 3
        assert "source_file" in merged.columns

    def test_merge_rejects_mismatched_columns(self, tmp_path):
        pd.DataFrame({"a": [1]}).to_excel(tmp_path / "x.xlsx", index=False)
        pd.DataFrame({"z": [1]}).to_excel(tmp_path / "y.xlsx", index=False)
        with pytest.raises(xt.ExcelToolsError):
            xt.merge_files([tmp_path / "x.xlsx", tmp_path / "y.xlsx"])

    def test_split(self, tmp_path):
        frame = pd.DataFrame({"branch": ["A", "A", "B"], "v": [1, 2, 3]})
        source = tmp_path / "all.xlsx"
        frame.to_excel(source, index=False)
        files = xt.split_file(source, "branch", tmp_path / "out")
        assert len(files) == 2

    def test_clean_actions(self):
        messy = pd.DataFrame(
            {
                "Loan ID": ["  L1 ", "L2", "L2"],
                "Paid On": ["2026-01-05", "2026-01-06", "2026-01-06"],
                "Empty": [None, None, None],
            }
        )
        report = xt.clean(messy)
        assert "loan_id" in report.frame.columns
        assert len(report.frame) == 2  # duplicate dropped
        assert any("dates" in a for a in report.actions)

    def test_compare(self):
        left = pd.DataFrame({"id": ["1", "2"], "v": ["a", "b"]})
        right = pd.DataFrame({"id": ["2", "3"], "v": ["B", "c"]})
        result = xt.compare_files(left, right, key="id")
        assert len(result.only_left) == 1
        assert len(result.only_right) == 1
        assert len(result.changed) == 1
        assert not result.identical

    def test_excel_sql_roundtrip(self, tmp_path, connections):
        frame = pd.DataFrame({"x": [1, 2, 3]})
        source = tmp_path / "in.xlsx"
        frame.to_excel(source, index=False)
        engine = connections.engine("test")
        rows = xt.excel_to_sql(source, engine, "roundtrip_test")
        assert rows == 3
        back = connections.run_query("test", "SELECT * FROM roundtrip_test").frame
        assert list(back["x"]) == [1, 2, 3]

    def test_profile(self):
        frame = pd.DataFrame({"a": [1, None, 3]})
        prof = xt.profile(frame)
        assert prof.iloc[0]["missing"] == 1


class TestNlq:
    def test_branch_ranking(self, nlq):
        answer = nlq.ask("top 3 branches by overdue")
        assert answer.ok and answer.intent == "branch_ranking"
        assert len(answer.frame) <= 3
        assert "ORDER BY" in answer.sql

    def test_highest_collections(self, nlq):
        answer = nlq.ask("show me branches with highest collections")
        assert answer.intent == "branch_ranking"
        assert "collected" in answer.frame.columns[1]

    def test_trend(self, nlq):
        answer = nlq.ask("collections trend last 45 days")
        assert answer.intent == "trend"
        assert len(answer.frame) == 46

    def test_overdue_loans_and_npa(self, nlq):
        assert nlq.ask("overdue loans").intent == "overdue_loans"
        assert nlq.ask("list npa loans").intent == "npa_list"

    def test_summary_and_mix(self, nlq):
        assert nlq.ask("business summary").intent == "summary"
        assert nlq.ask("product mix").intent == "product_mix"

    def test_unknown_gives_suggestions_not_guesses(self, nlq):
        answer = nlq.ask("what is the meaning of life")
        assert not answer.ok
        assert answer.suggestions


class TestAnalytics:
    def test_forecast(self, analytics):
        forecast = analytics.collections_forecast(history_days=60, horizon_days=14)
        assert len(forecast.forecast) == 14
        assert forecast.expected_total >= 0
        assert (forecast.forecast["predicted"] >= 0).all()

    def test_anomalies(self, analytics):
        anomalies = analytics.collection_anomalies(days=60)
        assert "zscore" in anomalies.frame.columns or anomalies.frame.empty

    def test_segments(self, analytics):
        segmentation = analytics.customer_segments(k=3)
        assert len(segmentation.profile) == 3
        assert set(segmentation.profile["label"]).issubset(
            {
                "High Risk / Deep Delinquent",
                "Watchlist / Irregular Payers",
                "Prime / On-time Payers",
                "Stable / Minor Slippage",
            }
        )

    def test_risk_scores(self, analytics):
        risk = analytics.loan_risk_scores()
        assert (risk.frame["risk_score"].between(0, 100)).all()
        assert risk.auc_like > 0  # NPAs must score higher on average
        assert "closed" not in set(risk.frame["status"])


class TestMis:
    def test_daily_pack(self, executive, tmp_path):
        generator = MisGenerator(executive)
        output = generator.generate("daily", out_dir=tmp_path)
        assert output.excel_path.exists()
        assert output.html_path.exists()
        sheets = pd.read_excel(output.excel_path, sheet_name=None)
        assert {"Summary", "Branches", "Insights"}.issubset(sheets)
        html = output.html_path.read_text(encoding="utf-8")
        assert "Executive insights" in html

    def test_invalid_period(self, executive):
        with pytest.raises(ValueError):
            MisGenerator(executive).generate("hourly")


class TestAutomation:
    def test_run_job_logs(self, appdb):
        center = AutomationCenter(appdb, poll_seconds=5)
        center.register_job("ok-job", lambda: "did it")
        assert center.run_job("ok-job") == "did it"
        runs = appdb.job_runs()
        assert runs[0]["job"] == "ok-job" and runs[0]["status"] == "success"

    def test_failed_job_logged(self, appdb):
        center = AutomationCenter(appdb, poll_seconds=5)

        def boom() -> str:
            raise RuntimeError("nope")

        center.register_job("bad-job", boom)
        with pytest.raises(RuntimeError):
            center.run_job("bad-job")
        assert appdb.job_runs()[0]["status"] == "failed"

    def test_schedule_validation(self, appdb):
        center = AutomationCenter(appdb)
        center.register_job("j", lambda: "x")
        with pytest.raises(ValueError):
            center.add_schedule(Schedule(job="unknown", every_minutes=5))
        with pytest.raises(ValueError):
            center.add_schedule(Schedule(job="j"))  # no trigger
        center.add_schedule(Schedule(job="j", every_minutes=5))
        assert len(center.schedules()) == 1

    def test_watch_fires_on_new_file(self, appdb, tmp_path):
        center = AutomationCenter(appdb, poll_seconds=5)
        fired: list[str] = []
        center.register_job("on-file", lambda: fired.append("yes") or "fired")
        center.add_watch(Watch(folder=str(tmp_path), pattern="*.csv", job="on-file"))
        (tmp_path / "statement.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        center._tick(__import__("datetime").datetime.now())  # noqa: SLF001 - direct tick
        assert fired == ["yes"]

    def test_daily_schedule_next_due(self):
        from datetime import datetime

        schedule = Schedule(job="j", daily_at="07:30")
        now = datetime(2026, 7, 24, 9, 0)
        assert schedule.next_due(now) <= now  # missed slot → run now
        schedule.last_run = datetime(2026, 7, 24, 7, 30)
        assert schedule.next_due(now).day == 25


class TestProductivity:
    def test_notes_tasks_pins(self, appdb):
        service = ProductivityService(appdb)
        note_id = service.save_note("Meeting", "CEO wants branch pack")
        assert any(n["id"] == note_id for n in service.notes())
        task_id = service.add_task("Prepare MIS")
        service.move_task(task_id, "doing")
        assert any(t["id"] == task_id for t in service.board().doing)
        service.pin("report", "daily_mis", "Daily MIS")
        assert service.pinned("report")[0]["ref"] == "daily_mis"
        with pytest.raises(ValueError):
            service.add_task("   ")


class TestScheduleLoop:
    def test_loop_start_stop_fast(self, appdb):
        center = AutomationCenter(appdb, poll_seconds=5)
        center.register_job("noop", lambda: "ok")
        center.start()
        time.sleep(0.1)
        center.stop()  # must not hang
