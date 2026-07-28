"""Tests for the Visual MIS Builder engine."""

from __future__ import annotations

import pandas as pd
import pytest

from finsight.modules.mis_builder import (
    BuilderConfig,
    SavedReport,
    build_pivot,
    delete_report,
    export_pivot,
    get_report,
    list_reports,
    save_report,
)
from finsight.modules.mis_samples import sample_lending_dataset


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "city": ["Kolkata", "Kolkata", "Delhi", "Delhi", "Pune"],
            "product": ["PL", "EL", "PL", "PL", "EL"],
            "amount": [100.0, 200.0, 300.0, 100.0, 50.0],
        }
    )


class TestBuildPivot:
    def test_sum_matches_manual_groupby(self):
        result = build_pivot(_df(), BuilderConfig("city", "amount", "Sum"))
        body = result.frame[result.frame["city"] != "TOTAL"].set_index("city")
        assert body.loc["Delhi"].iloc[0] == 400.0
        assert body.loc["Kolkata"].iloc[0] == 300.0

    def test_total_row_and_sorting(self):
        result = build_pivot(_df(), BuilderConfig("city", "amount", "Sum"))
        assert result.frame.iloc[0]["city"] == "Delhi"  # largest first
        assert result.frame.iloc[-1]["city"] == "TOTAL"
        assert result.frame.iloc[-1, 1] == 750.0

    def test_average_total_is_overall_mean(self):
        result = build_pivot(_df(), BuilderConfig("city", "amount", "Average"))
        assert result.frame.iloc[-1, 1] == pytest.approx(150.0)

    def test_count_aggregate(self):
        result = build_pivot(_df(), BuilderConfig("city", "amount", "Count"))
        assert result.frame.iloc[-1, 1] == 5

    def test_split_by_second_dimension(self):
        result = build_pivot(_df(), BuilderConfig("city", "amount", "Sum", split_by="product"))
        assert {"EL", "PL"} <= set(result.frame.columns)
        delhi = result.frame[result.frame["city"] == "Delhi"].iloc[0]
        assert delhi["PL"] == 400.0 and delhi["EL"] == 0.0

    def test_friendly_error_for_missing_column(self):
        with pytest.raises(ValueError, match="not in this file"):
            build_pivot(_df(), BuilderConfig("branch", "amount", "Sum"))

    def test_same_group_and_split_rejected(self):
        with pytest.raises(ValueError, match="must be different"):
            build_pivot(_df(), BuilderConfig("city", "amount", "Sum", split_by="city"))

    def test_empty_frame_rejected(self):
        with pytest.raises(ValueError, match="no rows"):
            build_pivot(pd.DataFrame(), BuilderConfig("city", "amount", "Sum"))

    def test_sample_dataset_works(self):
        result = build_pivot(
            sample_lending_dataset(150),
            BuilderConfig("branch", "loan_amount", "Sum", split_by="product"),
        )
        assert len(result.frame) > 2


class TestExport:
    def test_excel_export(self, tmp_path):
        result = build_pivot(_df(), BuilderConfig("city", "amount", "Sum"))
        out = export_pivot(result, tmp_path / "pivot.xlsx")
        assert out.is_file()
        read_back = pd.read_excel(out, skiprows=2)
        assert len(read_back) == len(result.frame)

    def test_csv_export(self, tmp_path):
        result = build_pivot(_df(), BuilderConfig("city", "amount", "Sum"))
        out = export_pivot(result, tmp_path / "pivot.csv")
        assert len(pd.read_csv(out)) == len(result.frame)


class TestRobustCoercionAndNewAggregates:
    def test_text_money_column_sums_correctly(self):
        df = pd.DataFrame(
            {
                "city": ["A", "A", "B"],
                "amount": ["Rs 1,000.00", "(250)", "INR 2,500"],
            }
        )
        result = build_pivot(df, BuilderConfig("city", "amount", "Sum"))
        total = result.frame.iloc[-1]
        assert total[result.frame.columns[0]] == "TOTAL"
        assert total.iloc[1] == 3250.0  # 1000 - 250 + 2500

    def test_median_total_recomputed_over_whole_dataset(self):
        df = pd.DataFrame({"city": ["A", "A", "B", "B", "B"], "amount": [10, 20, 30, 40, 500]})
        result = build_pivot(df, BuilderConfig("city", "amount", "Median"))
        assert result.frame.iloc[-1, 1] == 30.0  # overall median, not median of medians

    def test_count_distinct_total_is_overall_nunique(self):
        df = pd.DataFrame(
            {
                "city": ["A", "A", "B", "B"],
                "customer": ["riya", "arjun", "riya", "mou"],
            }
        )
        result = build_pivot(df, BuilderConfig("city", "customer", "Count Distinct"))
        # per-group: A=2, B=2 -> naive sum 4; correct overall distinct = 3
        assert result.frame.iloc[-1, 1] == 3.0

    def test_fully_blank_rows_dropped(self):
        df = pd.DataFrame({"city": ["A", None, "B"], "amount": [10.0, None, 30.0]})
        result = build_pivot(df, BuilderConfig("city", "amount", "Sum"))
        groups = result.frame.iloc[:, 0].tolist()
        assert "(blank)" not in groups
        assert result.frame.iloc[-1, 1] == 40.0


class TestSavedReports:
    def test_roundtrip_update_delete(self, tmp_path):
        store = tmp_path / "store.json"
        config = BuilderConfig("city", "amount", "Sum", split_by="product")
        save_report(SavedReport("Weekly", "/data/x.csv", config), path=store)
        save_report(SavedReport("Weekly", "/data/y.csv", config), path=store)  # overwrite
        reports = list_reports(path=store)
        assert len(reports) == 1 and reports[0].source_path == "/data/y.csv"
        assert get_report("Weekly", path=store).config == config
        delete_report("Weekly", path=store)
        assert list_reports(path=store) == []

    def test_empty_name_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="name"):
            save_report(
                SavedReport("  ", "x.csv", BuilderConfig("a", "b", "Sum")),
                path=tmp_path / "s.json",
            )
