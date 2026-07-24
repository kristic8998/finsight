"""Data layer + executive service tests against the generated demo book."""

from __future__ import annotations

import pytest

from finsight.core.config import DemoConfig
from finsight.data.connections import ConnectionError_
from finsight.data.demo_data import generate_demo_db


class TestDemoData:
    def test_generation_counts(self, demo_db, config):
        summary = generate_demo_db(config.demo, path=demo_db)  # idempotent reuse
        assert summary.loans == config.demo.loans
        assert summary.branches == config.demo.branches
        assert summary.payments > summary.loans  # multiple installments per loan

    def test_deterministic_per_seed(self, tmp_path):
        cfg = DemoConfig(seed=99, branches=3, loans=60)
        a = generate_demo_db(cfg, path=tmp_path / "a.db", force=True)
        b = generate_demo_db(cfg, path=tmp_path / "b.db", force=True)
        assert a.payments == b.payments


class TestConnections:
    def test_demo_connection_always_exists(self, connections):
        names = [c.name for c in connections.list_connections()]
        assert "Demo Lending DB" in names

    def test_query_and_truncation(self, connections):
        result = connections.run_query("test", "SELECT * FROM loans", max_rows=50)
        assert result.truncated is True
        assert len(result.frame) == 50

    def test_non_select_statements(self, connections):
        connections.run_query("test", "CREATE TABLE IF NOT EXISTS scratch (x INT)")
        outcome = connections.run_query("test", "INSERT INTO scratch VALUES (1)")
        assert outcome.rows == 1

    def test_empty_sql_rejected(self, connections):
        with pytest.raises(ConnectionError_):
            connections.run_query("test", "   ")

    def test_unknown_connection(self, connections):
        with pytest.raises(ConnectionError_):
            connections.engine("nope")

    def test_list_tables(self, connections):
        tables = connections.list_tables("test")
        assert {"branches", "loans", "payments"}.issubset(set(tables))


class TestKpis:
    def test_kpis_are_coherent(self, data):
        kpis = data.kpis()
        assert kpis.portfolio_outstanding > 0
        assert kpis.active_loans > 0
        assert 0 <= kpis.efficiency_mtd <= 150
        assert 0 <= kpis.par_pct <= 100
        assert kpis.overdue_amount >= 0

    def test_branch_summary_ranked(self, data, config):
        summary = data.branch_summary()
        assert len(summary) == config.demo.branches
        assert list(summary["rank"]) == sorted(summary["rank"])
        assert summary.iloc[0]["score"] >= summary.iloc[-1]["score"]

    def test_dpd_buckets_shape(self, data):
        buckets = data.dpd_buckets()
        assert list(buckets["bucket"]) == ["1-30", "31-60", "61-90", "90+"]
        assert (buckets["amount"] >= 0).all()

    def test_daily_collections_window(self, data):
        series = data.daily_collections(days=30)
        assert len(series) == 31  # inclusive window
        assert (series["collected"] >= 0).all()

    def test_overdue_loans_filter(self, data):
        all_overdue = data.overdue_loans()
        assert (all_overdue["overdue_amount"] > 0).all()
        if len(all_overdue):
            branch = all_overdue.iloc[0]["branch"]
            filtered = data.overdue_loans(branch=branch)
            assert set(filtered["branch"]) == {branch}


class TestExecutive:
    def test_health_score_bounds(self, executive, data):
        health = executive.health_score(data.kpis())
        assert 0 <= health.score <= 100
        assert health.grade in ("A+", "A", "B", "C", "D")
        assert set(health.components) == {
            "collection_efficiency",
            "portfolio_quality",
            "target_achievement",
            "growth",
        }

    def test_brief_is_complete(self, executive):
        brief = executive.brief()
        assert brief.summary_text
        assert len(brief.insights) >= 1
        assert not brief.branches.empty
        severities = {i.severity for i in brief.insights}
        assert severities <= {"good", "watch", "alert"}

    def test_insights_react_to_thresholds(self, executive, data):
        # With impossible thresholds, the "all clear" insight appears.
        executive._config.par_alert_pct = 100.0  # noqa: SLF001
        executive._config.efficiency_alert_pct = 0.0  # noqa: SLF001
        executive._config.concentration_alert_pct = 100.0  # noqa: SLF001
        kpis = data.kpis()
        branches = data.branch_summary()
        mix = data.product_mix()
        insights = executive.insights(kpis, branches, mix)
        assert insights  # never empty
