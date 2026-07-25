"""Tests for the Data Quality Center profiler."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from finsight.modules.data_quality import (
    export_report,
    profile_chunks,
    profile_csv,
    profile_frame,
)


def _messy_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": [1, 2, 2, 4, 5, 6],  # duplicate key value (2)
            "amount": [100.0, 200.0, 200.0, None, -50.0, 100000.0],  # missing, negative, outlier
            "name": ["Acme", "Beta ", "beta", "Delta", "Echo", "Acme"],  # trailing space
            "flag": ["Y", "Y", "Y", "Y", "Y", "Y"],  # constant column
        }
    )


class TestProfileFrame:
    def test_shape_and_missing(self):
        report = profile_frame(_messy_frame())
        assert report.rows == 6
        assert report.columns == 4
        amount = next(p for p in report.column_profiles if p.name == "amount")
        assert amount.missing == 1
        assert amount.numeric_min == -50.0
        assert amount.numeric_max == 100000.0

    def test_detects_expected_issues(self):
        rules = {i.rule for i in profile_frame(_messy_frame()).issues}
        assert "duplicate keys" in rules  # id column has a repeat
        assert "constant column" in rules  # flag is all "Y"
        assert "negative amount" in rules  # amount has -50
        assert "whitespace" in rules  # "Beta " has a trailing space

    def test_duplicate_rows(self):
        frame = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
        report = profile_frame(frame)
        assert report.duplicate_rows == 1
        assert any(i.rule == "duplicate rows" for i in report.issues)

    def test_clean_data_scores_higher_than_messy(self):
        clean = pd.DataFrame({"id": [1, 2, 3, 4], "value": [10.0, 11.0, 12.0, 13.0]})
        assert profile_frame(clean).score > profile_frame(_messy_frame()).score
        assert profile_frame(clean).grade in {"A", "B"}

    def test_empty_column_is_alert(self):
        frame = pd.DataFrame({"id": [1, 2, 3], "blank": [None, None, None]})
        report = profile_frame(frame)
        issue = next(i for i in report.issues if i.column == "blank")
        assert issue.severity == "alert"
        assert issue.rule == "empty column"

    def test_outlier_detection(self):
        frame = pd.DataFrame({"n": [10, 11, 12, 10, 11, 9, 10, 5000]})
        report = profile_frame(frame)
        assert any(i.rule == "outliers" for i in report.issues)

    def test_score_bounds(self):
        report = profile_frame(_messy_frame())
        assert 0.0 <= report.score <= 100.0
        assert report.grade in {"A", "B", "C", "D", "F"}


class TestStreaming:
    def test_chunked_matches_whole(self):
        frame = _messy_frame()
        whole = profile_frame(frame)
        chunked = profile_chunks([frame.iloc[:2], frame.iloc[2:4], frame.iloc[4:]])
        assert chunked.rows == whole.rows
        assert chunked.duplicate_rows == whole.duplicate_rows
        assert chunked.score == whole.score
        whole_missing = {p.name: p.missing for p in whole.column_profiles}
        chunk_missing = {p.name: p.missing for p in chunked.column_profiles}
        assert chunk_missing == whole_missing

    def test_profile_csv_matches_frame(self, tmp_path):
        frame = pd.DataFrame({"id": list(range(100)) + [0], "v": list(np.arange(101, dtype=float))})
        csv_path = tmp_path / "data.csv"
        frame.to_csv(csv_path, index=False)
        streamed = profile_csv(csv_path, chunk_size=10)
        whole = profile_frame(frame)
        assert streamed.rows == whole.rows == 101
        assert streamed.duplicate_rows == whole.duplicate_rows
        assert streamed.columns == 2


class TestExport:
    def test_export_creates_three_sheets(self, tmp_path):
        report = profile_frame(_messy_frame())
        out = export_report(report, tmp_path / "dq.xlsx")
        assert out.is_file()
        sheets = pd.ExcelFile(out).sheet_names
        assert sheets == ["Summary", "Column Profiles", "Exceptions"]

    def test_issues_frame_columns(self):
        report = profile_frame(_messy_frame())
        frame = report.issues_frame()
        assert list(frame.columns) == ["severity", "rule", "column", "count", "detail"]


def test_empty_frame_is_safe():
    report = profile_frame(pd.DataFrame())
    assert report.rows == 0
    assert report.columns == 0
    assert report.score == pytest.approx(100.0)
