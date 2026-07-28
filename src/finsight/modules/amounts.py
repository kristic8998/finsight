"""Robust money/number coercion shared by every FinSight engine.

Real LMS/bank exports write amounts as text far more often than as numbers:
``"Rs 1,20,000.00"``, ``"INR 2,500"``, ``"₹ 999"``, accounting negatives
``"(2,500.00)"``, banker suffixes ``"1,250.00 Cr" / "500 Dr"`` and percents
``"24%"``. Plain ``pd.to_numeric`` silently coerces ALL of these to NaN,
which then reads as 0 in a report — a silent, plausible, wrong number.

House rule: this is the ONE money parser for the app. Engines must call
:func:`parse_amount_series` (or :func:`parse_amount`) instead of a bare
``pd.to_numeric`` whenever a column may contain money-like text.

Deliberately rejected (stay NaN): identifiers and prose that merely contain
digits (``"LN50021"``, ``"USDA grant 2026"``), booleans, and empty strings.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

# Currency markers we strip when they PREFIX a number ("Rs 500", "INR2,000",
# "₹ 999", "$1.50"). The digit lookahead keeps "Resolved" untouched.
_CURRENCY_PREFIX = re.compile(
    r"^(?:rs\.?|inr|npr|bdt|usd|eur|gbp|[₹$€£₨])\s*(?=[\d(.\-+])",
    re.IGNORECASE,
)
# Banker suffixes: "1,250.00 Cr" (credit, +) / "500 Dr" (debit, -).
_CRDR_SUFFIX = re.compile(r"\s*(cr|dr)\.?$", re.IGNORECASE)
_ALLOWED_RESIDUE = re.compile(r"^[+-]?\d*(?:\.\d+)?$")


def parse_amount(value: object) -> float:
    """Best-effort conversion of one cell to ``float`` (NaN when not a number)."""
    if value is None or isinstance(value, bool):
        return float("nan")
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    text = str(value).strip()
    if not text or not any(ch.isdigit() for ch in text):
        return float("nan")

    negative = False
    suffix = _CRDR_SUFFIX.search(text)
    if suffix:  # banker suffix comes outermost: "(300) Cr", "500 Dr"
        if suffix.group(1).lower() == "dr":
            negative = not negative
        text = text[: suffix.start()].strip()

    if text.startswith("(") and text.endswith(")"):  # accounting negative
        negative, text = not negative, text[1:-1].strip()

    text = _CURRENCY_PREFIX.sub("", text)
    if text.endswith("%"):
        text = text[:-1].strip()
    # tolerate grouping/format noise only: commas, spaces, underscores
    text = text.replace(",", "").replace(" ", "").replace("_", "")
    if not _ALLOWED_RESIDUE.match(text):
        return float("nan")  # letters left over -> an identifier, not an amount
    try:
        number = float(text)
    except ValueError:
        return float("nan")
    return -number if negative else number


def parse_amount_series(series: pd.Series) -> pd.Series:
    """Vectorised :func:`parse_amount` with a fast path for numeric columns."""
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return series.astype(float)
    return series.map(parse_amount).astype(float)
