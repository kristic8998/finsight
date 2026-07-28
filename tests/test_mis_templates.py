"""Tests for the One-Click Lending Templates."""

from __future__ import annotations

import pandas as pd
import pytest

from finsight.modules.mis_samples import sample_lending_dataset
from finsight.modules.mis_templates import (
    TEMPLATES,
    TemplateError,
    export_template,
    run_template,
)


class TestDailyDisbursement:
    def test_kpis_and_sheets(self):
        result = run_template("daily_disbursement", sample_lending_dataset(200))
        labels = [label for label, _v in result.kpis]
        assert "Total disbursed" in labels and "Average ticket" in labels
        assert {"By Branch", "By Product", "Daily Trend"} <= set(result.sheets)
        branch_sheet = result.sheets["By Branch"]
        assert str(branch_sheet.iloc[-1, 0]) == "TOTAL"

    def test_total_matches_input(self):
        df = sample_lending_dataset(200)
        result = run_template("daily_disbursement", df)
        total = result.sheets["By Branch"].iloc[-1]["disbursed"]
        assert total == pytest.approx(df["loan_amount"].sum())

    def test_missing_amount_is_friendly(self):
        with pytest.raises(TemplateError, match="loan amount column"):
            run_template("daily_disbursement", pd.DataFrame({"branch": ["x"]}))

    def test_no_date_column_noted_not_fatal(self):
        df = sample_lending_dataset(80).drop(columns=["disbursed_date"])
        result = run_template("daily_disbursement", df)
        assert "Daily Trend" not in result.sheets
        assert any("date" in note for note in result.notes)


class TestCollectionDpd:
    def test_buckets_and_par(self):
        df = sample_lending_dataset(300)
        result = run_template("collection_dpd", df)
        buckets = result.sheets["DPD Buckets"]
        assert {"Current", "1-30", "90+"} <= set(buckets.columns)
        par30 = next(v for label, v in result.kpis if label == "PAR 30")
        assert par30.endswith("%")
        assert "Collection Efficiency" in result.sheets  # sample has due/paid

    def test_bucket_counts_add_up(self):
        df = sample_lending_dataset(300)
        result = run_template("collection_dpd", df)
        totals = result.sheets["DPD Buckets"].iloc[-1]
        bucket_cols = ["Current", "1-30", "31-60", "61-90", "90+"]
        assert int(sum(totals[c] for c in bucket_cols)) == len(df)

    def test_missing_dpd_is_friendly(self):
        with pytest.raises(TemplateError, match="DPD column"):
            run_template("collection_dpd", pd.DataFrame({"amount": [1.0]}))


class TestPortfolioHealth:
    def test_concentration_shares_sum_to_100(self):
        result = run_template("portfolio_health", sample_lending_dataset(250))
        by_branch = result.sheets["By Branch"]
        body = by_branch[by_branch["branch"] != "TOTAL"]
        assert body["share_pct"].sum() == pytest.approx(100.0, abs=1.5)
        assert len(result.sheets["Top 20 Exposures"]) == 20

    def test_missing_outstanding_is_friendly(self):
        with pytest.raises(TemplateError, match="outstanding"):
            run_template("portfolio_health", pd.DataFrame({"name": ["x"]}))


class TestGeneral:
    def test_unknown_template_rejected(self):
        with pytest.raises(ValueError, match="unknown template"):
            run_template("nope", sample_lending_dataset(10))

    def test_empty_file_is_friendly(self):
        with pytest.raises(TemplateError, match="no rows"):
            run_template("portfolio_health", pd.DataFrame())

    def test_export_all_templates(self, tmp_path):
        df = sample_lending_dataset(150)
        for key in TEMPLATES:
            out = export_template(run_template(key, df), tmp_path / f"{key}.xlsx")
            sheets = pd.ExcelFile(out).sheet_names
            assert sheets[0] == "Summary" and len(sheets) >= 3


class TestTextMoneyAndBlankRows:
    def test_text_money_amounts_are_totalled(self):
        df = sample_lending_dataset(50)
        df["loan_amount"] = df["loan_amount"].map(lambda v: f"Rs {v:,.2f}")
        result = run_template("daily_disbursement", df)
        # the Rs-worded text amounts must sum to the same real total
        clean_total = sample_lending_dataset(50)["loan_amount"].sum()
        got = result.sheets["By Branch"].iloc[-1]["disbursed"]
        assert got == pytest.approx(clean_total)

    def test_fully_blank_rows_are_ignored(self):
        df = sample_lending_dataset(30)
        blank = pd.DataFrame([{c: pd.NA for c in df.columns}]).astype(object)
        noisy = pd.concat([df.astype(object), blank], ignore_index=True)
        result = run_template("portfolio_health", noisy)
        clean = run_template("portfolio_health", df)
        assert result.kpis[0] == clean.kpis[0]

    def test_all_blank_file_raises_friendly_error(self):
        df = pd.DataFrame({"loan_amount": [None, None], "branch": [None, None]})
        with pytest.raises(TemplateError, match="no data rows"):
            run_template("daily_disbursement", df)
