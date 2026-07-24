"""Reconciliation engine.

General two-source reconciliation (ledger vs gateway, bank vs
collections, settlement vs ledger): exact key matching, amount
comparison within a configurable tolerance, duplicate detection on both
sides, and a styled multi-sheet Excel difference report. Works on any
pair of DataFrames — Excel/CSV upload or SQL result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


class ReconError(Exception):
    """Raised for unusable reconciliation inputs."""


@dataclass
class ReconResult:
    """Everything a mismatch report needs."""

    matched: pd.DataFrame
    amount_mismatch: pd.DataFrame
    only_left: pd.DataFrame
    only_right: pd.DataFrame
    dup_left: pd.DataFrame
    dup_right: pd.DataFrame
    left_name: str = "Left"
    right_name: str = "Right"
    key: str = ""
    tolerance: float = 0.0
    stats: dict[str, float] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        s = self.stats
        return (
            f"{int(s['matched'])} matched, {int(s['amount_mismatch'])} amount mismatches, "
            f"{int(s['only_left'])} only in {self.left_name}, "
            f"{int(s['only_right'])} only in {self.right_name}, "
            f"{int(s['dup_left']) + int(s['dup_right'])} duplicates. "
            f"Net difference {s['net_difference']:,.2f}."
        )


def _normalise(frame: pd.DataFrame, key: str, amount: str) -> pd.DataFrame:
    if key not in frame.columns:
        raise ReconError(f"key column '{key}' not found (has: {list(frame.columns)})")
    if amount not in frame.columns:
        raise ReconError(f"amount column '{amount}' not found (has: {list(frame.columns)})")
    out = frame.copy()
    out[key] = out[key].astype(str).str.strip()
    out[amount] = pd.to_numeric(out[amount], errors="coerce")
    if out[amount].isna().any():
        bad = int(out[amount].isna().sum())
        raise ReconError(f"{bad} non-numeric value(s) in amount column '{amount}'")
    return out


def reconcile(
    left: pd.DataFrame,
    right: pd.DataFrame,
    key: str,
    amount: str,
    tolerance: float = 0.0,
    left_name: str = "Ledger",
    right_name: str = "Statement",
) -> ReconResult:
    """Reconcile two frames on ``key``, comparing ``amount`` within tolerance."""
    left_n = _normalise(left, key, amount)
    right_n = _normalise(right, key, amount)

    dup_left = left_n[left_n.duplicated(key, keep=False)].sort_values(key)
    dup_right = right_n[right_n.duplicated(key, keep=False)].sort_values(key)

    # Aggregate duplicates by key so the compare is well-defined; the
    # duplicate frames above preserve the originals for investigation.
    left_agg = left_n.groupby(key, as_index=False)[amount].sum()
    right_agg = right_n.groupby(key, as_index=False)[amount].sum()

    merged = left_agg.merge(
        right_agg, on=key, how="outer", suffixes=("_left", "_right"), indicator=True
    )
    amount_l, amount_r = f"{amount}_left", f"{amount}_right"

    only_left = merged[merged["_merge"] == "left_only"][[key, amount_l]].rename(
        columns={amount_l: amount}
    )
    only_right = merged[merged["_merge"] == "right_only"][[key, amount_r]].rename(
        columns={amount_r: amount}
    )

    both = merged[merged["_merge"] == "both"].copy()
    both["difference"] = (both[amount_l] - both[amount_r]).round(2)
    within = both["difference"].abs() <= tolerance
    matched = both[within][[key, amount_l, amount_r, "difference"]]
    mismatch = both[~within][[key, amount_l, amount_r, "difference"]].sort_values(
        "difference", key=lambda s: s.abs(), ascending=False
    )

    stats = {
        "matched": float(len(matched)),
        "amount_mismatch": float(len(mismatch)),
        "only_left": float(len(only_left)),
        "only_right": float(len(only_right)),
        "dup_left": float(len(dup_left)),
        "dup_right": float(len(dup_right)),
        "left_total": round(float(left_n[amount].sum()), 2),
        "right_total": round(float(right_n[amount].sum()), 2),
        "net_difference": round(float(left_n[amount].sum() - right_n[amount].sum()), 2),
        "match_rate_pct": round(len(matched) / len(both) * 100, 1) if len(both) else 0.0,
    }
    return ReconResult(
        matched=matched.reset_index(drop=True),
        amount_mismatch=mismatch.reset_index(drop=True),
        only_left=only_left.reset_index(drop=True),
        only_right=only_right.reset_index(drop=True),
        dup_left=dup_left.reset_index(drop=True),
        dup_right=dup_right.reset_index(drop=True),
        left_name=left_name,
        right_name=right_name,
        key=key,
        tolerance=tolerance,
        stats=stats,
    )


def export_recon_report(result: ReconResult, path: Path | str) -> Path:
    """Write the classic multi-tab difference workbook (colour-coded tabs)."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summary = pd.DataFrame(
        {
            "metric": [
                "matched",
                "amount_mismatch",
                f"only_in_{result.left_name}",
                f"only_in_{result.right_name}",
                "duplicates_left",
                "duplicates_right",
                "left_total",
                "right_total",
                "net_difference",
                "match_rate_pct",
            ],
            "value": [
                result.stats["matched"],
                result.stats["amount_mismatch"],
                result.stats["only_left"],
                result.stats["only_right"],
                result.stats["dup_left"],
                result.stats["dup_right"],
                result.stats["left_total"],
                result.stats["right_total"],
                result.stats["net_difference"],
                result.stats["match_rate_pct"],
            ],
        }
    )
    sheets = {
        "Summary": summary,
        "Matched": result.matched,
        "Amount Mismatch": result.amount_mismatch,
        f"Only {result.left_name}"[:31]: result.only_left,
        f"Only {result.right_name}"[:31]: result.only_right,
        "Duplicates Left": result.dup_left,
        "Duplicates Right": result.dup_right,
    }
    colors = {
        "Summary": "1F4E79",
        "Matched": "2E7D32",
        "Amount Mismatch": "C62828",
        f"Only {result.left_name}"[:31]: "EF6C00",
        f"Only {result.right_name}"[:31]: "EF6C00",
        "Duplicates Left": "6A1B9A",
        "Duplicates Right": "6A1B9A",
    }
    from .investigate import investigate

    inv = investigate(result)
    sheets["Investigation"] = inv.to_frame()
    colors["Investigation"] = "1F4E79"
    if len(inv.typo_pairs):
        sheets["Possible Typos"] = inv.typo_pairs
        colors["Possible Typos"] = "EF6C00"

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
            sheet = writer.sheets[sheet_name]
            sheet.sheet_properties.tabColor = colors.get(sheet_name, "888888")
            sheet.freeze_panes = "A2"
            for column_cells in sheet.columns:
                width = max(
                    (len(str(c.value)) for c in column_cells if c.value is not None), default=8
                )
                sheet.column_dimensions[column_cells[0].column_letter].width = min(width + 2, 40)
    return out_path
