"""Tests: root-cause investigation, typo detection, quality scoring."""

from __future__ import annotations

import pandas as pd
import pytest

from finsight.modules.investigate import investigate, quality_score
from finsight.modules.recon import export_recon_report, reconcile


@pytest.fixture()
def rich_recon():
    """A reconciliation with every cause present, including a typo pair."""
    ledger = pd.DataFrame(
        {
            "utr": ["T1", "T2", "T3", "T4", "T4", "UTR-9001"],
            "amount": [100.0, 200.0, 300.0, 50.0, 50.0, 999.0],
        }
    )
    bank = pd.DataFrame(
        {
            "utr": ["T1", "T2", "T5", "UTR9001"],
            "amount": [100.0, 210.0, 75.0, 999.0],
        }
    )
    return reconcile(
        ledger, bank, key="utr", amount="amount", left_name="Ledger", right_name="Bank"
    )


class TestInvestigation:
    def test_decomposition_covers_all_causes(self, rich_recon):
        inv = investigate(rich_recon)
        categories = {c.category for c in inv.causes}
        assert "missing in Bank" in categories
        assert "missing in Ledger" in categories
        assert "amount mismatches" in categories
        assert "duplicate keys" in categories
        assert all(c.recommendation for c in inv.causes)

    def test_causes_ranked_by_impact(self, rich_recon):
        inv = investigate(rich_recon)
        impacts = [abs(c.amount_impact) for c in inv.causes]
        assert impacts == sorted(impacts, reverse=True)
        assert all(0 <= c.share_pct <= 100 for c in inv.causes)

    def test_typo_pair_detected(self, rich_recon):
        inv = investigate(rich_recon)
        assert len(inv.typo_pairs) >= 1
        pair = inv.typo_pairs.iloc[0]
        assert {pair["left_key"], pair["right_key"]} == {"UTR-9001", "UTR9001"}
        assert pair["similarity"] >= 0.85
        assert "typo" in inv.narrative.lower()

    def test_narrative_mentions_net_difference(self, rich_recon):
        inv = investigate(rich_recon)
        assert f"{inv.net_difference:,.2f}" in inv.narrative
        assert inv.to_frame().shape[0] == len(inv.causes)

    def test_fully_matched_recon_has_no_causes(self):
        same = pd.DataFrame({"utr": ["A", "B"], "amount": [1.0, 2.0]})
        result = reconcile(same, same.copy(), key="utr", amount="amount")
        inv = investigate(result)
        assert inv.causes == []
        assert "fully explained" in inv.narrative

    def test_export_includes_investigation_sheet(self, rich_recon, tmp_path):
        path = export_recon_report(rich_recon, tmp_path / "r.xlsx")
        sheets = pd.read_excel(path, sheet_name=None)
        assert "Investigation" in sheets
        assert "Possible Typos" in sheets
        assert not sheets["Investigation"].empty


class TestQualityScore:
    def test_perfect_data_scores_high(self):
        clean = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        score = quality_score(clean)
        assert score.overall >= 95
        assert score.grade == "A"

    def test_messy_data_scores_lower_with_notes(self):
        messy = pd.DataFrame(
            {
                "a": [1, 1, None, None],
                "b": ["1", "text", "2", "3"],  # mixed types
            }
        )
        messy = pd.concat([messy, messy.iloc[[0]]], ignore_index=True)  # dup row
        score = quality_score(messy)
        assert score.overall < 90
        assert score.completeness < 100
        assert score.uniqueness < 100
        assert any("mixes" in n for n in score.notes)

    def test_empty_frame(self):
        score = quality_score(pd.DataFrame())
        assert score.overall == 0.0
        assert score.grade == "F"
