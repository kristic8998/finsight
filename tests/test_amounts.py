"""Tests for the shared money/number parser."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from finsight.modules.amounts import parse_amount, parse_amount_series


class TestParseAmount:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (1500, 1500.0),
            (99.5, 99.5),
            ("1500", 1500.0),
            ("1,20,000.00", 120000.0),
            ("Rs 1,20,000.00", 120000.0),
            ("Rs. 500", 500.0),
            ("INR 2,500", 2500.0),
            ("₹ 999", 999.0),
            ("$1.50", 1.5),
            ("(2,500.00)", -2500.0),
            ("1,250.00 Cr", 1250.0),
            ("500 Dr", -500.0),
            ("(300) Cr", -300.0),
            ("24%", 24.0),
            ("-750", -750.0),
            ("+750", 750.0),
            ("1 200,50".replace(",", "."), 1200.5),  # "1 200.50" spaced grouping
        ],
    )
    def test_parses(self, raw, expected):
        assert parse_amount(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            None,
            True,
            False,
            "Resolved",
            "USDA grant",
            "LN50021",
            "LAN200000",
            "12-34-56",
            "1.2.3",
            "n/a",
            "—",
        ],
    )
    def test_rejects(self, raw):
        assert math.isnan(parse_amount(raw))


class TestParseAmountSeries:
    def test_numeric_fast_path(self):
        s = pd.Series([1, 2, 3])
        out = parse_amount_series(s)
        assert out.tolist() == [1.0, 2.0, 3.0]
        assert out.dtype == float

    def test_mixed_text_column(self):
        s = pd.Series(["Rs 1,000", "(250)", "bad", None, 50])
        out = parse_amount_series(s)
        assert out.iloc[0] == 1000.0
        assert out.iloc[1] == -250.0
        assert math.isnan(out.iloc[2])
        assert math.isnan(out.iloc[3])
        assert out.iloc[4] == 50.0

    def test_bool_series_not_treated_as_numbers(self):
        out = parse_amount_series(pd.Series([True, False]))
        assert out.isna().all()
