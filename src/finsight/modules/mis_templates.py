"""One-Click Lending Templates — pre-built MIS intelligence.

Pure pandas, no UI. Each template takes a raw LMS export (columns are
detected by name hints, so real-world files work without a fixed
schema), applies the lending business logic, and produces a
:class:`TemplateResult` — headline KPIs plus named sheets — which
:func:`export_template` turns into a formatted, CEO-ready workbook.

A file that cannot serve a template raises :class:`TemplateError` with a
plain-English message; the UI shows it as a friendly popup, never a
crash.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .excel_style import write_formatted_sheet

DPD_BUCKETS = ((0, "Current"), (30, "1-30"), (60, "31-60"), (90, "61-90"), (10**9, "90+"))


class TemplateError(ValueError):
    """A friendly, user-facing problem with the uploaded file."""


@dataclass(frozen=True)
class TemplateSpec:
    key: str
    title: str
    icon: str
    tagline: str
    needs: str  # human description of the minimum columns


TEMPLATES: dict[str, TemplateSpec] = {
    "daily_disbursement": TemplateSpec(
        key="daily_disbursement",
        title="Daily Disbursement MIS",
        icon="🏦",
        tagline="How much did we lend, where, and in what?",
        needs="a loan amount column (date / branch / product are used when present)",
    ),
    "collection_dpd": TemplateSpec(
        key="collection_dpd",
        title="Collection & DPD MIS",
        icon="📞",
        tagline="Who is overdue, how badly, and how is collection going?",
        needs="a DPD (days past due) column (outstanding / EMI due & paid enrich it)",
    ),
    "portfolio_health": TemplateSpec(
        key="portfolio_health",
        title="Portfolio Health Report",
        icon="❤️",
        tagline="Book size, PAR ratios, concentration, top exposures.",
        needs="an outstanding (or loan amount) column (DPD / branch / product enrich it)",
    ),
}


@dataclass
class TemplateResult:
    key: str
    title: str
    kpis: list[tuple[str, str]]
    sheets: dict[str, pd.DataFrame]
    notes: list[str] = field(default_factory=list)

    def summary_text(self) -> str:
        head = " · ".join(f"{label}: {value}" for label, value in self.kpis[:3])
        return f"{self.title} — {head}"


# ---- column detection ---------------------------------------------------------
def _find(frame: pd.DataFrame, hints: tuple[str, ...]) -> str | None:
    lowered = {str(c).strip().lower(): str(c) for c in frame.columns}
    for hint in hints:
        if hint in lowered:
            return lowered[hint]
    for hint in hints:
        for low, original in lowered.items():
            if hint in low:
                return original
    return None


def _num(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _text(frame: pd.DataFrame, column: str | None, default: str) -> pd.Series:
    if column is None:
        return pd.Series(default, index=frame.index)
    return frame[column].fillna(default).astype(str)


def _rs(value: float) -> str:
    return f"Rs {value:,.0f}"


def _with_total(frame: pd.DataFrame, label_col: str) -> pd.DataFrame:
    totals: dict[str, object] = {label_col: "TOTAL"}
    for column in frame.columns:
        if column != label_col and pd.api.types.is_numeric_dtype(frame[column]):
            totals[column] = frame[column].sum()
    return pd.concat([frame, pd.DataFrame([totals])], ignore_index=True)


def _bucket(dpd: pd.Series) -> pd.Series:
    edges = [-1] + [limit for limit, _label in DPD_BUCKETS]
    labels = [label for _limit, label in DPD_BUCKETS]
    return pd.cut(dpd, bins=edges, labels=labels).astype(str)


# ---- templates -----------------------------------------------------------------
def _daily_disbursement(df: pd.DataFrame) -> TemplateResult:
    amount_col = _find(df, ("loan_amount", "disbursed_amount", "principal", "amount"))
    if amount_col is None:
        raise TemplateError(
            "This template needs a loan amount column (e.g. 'loan_amount' or "
            "'disbursed_amount'). Please upload the disbursement export from your LMS."
        )
    amount = _num(df, amount_col)
    branch = _text(df, _find(df, ("branch", "city", "region", "location")), "(all)")
    product = _text(df, _find(df, ("product", "scheme", "loan_type")), "(all)")
    date_col = _find(df, ("disbursed_date", "disbursal", "date"))
    notes: list[str] = []

    by_branch = (
        pd.DataFrame({"branch": branch, "disbursed": amount, "loans": 1})
        .groupby("branch", as_index=False)
        .agg(disbursed=("disbursed", "sum"), loans=("loans", "count"))
        .assign(avg_ticket=lambda d: (d["disbursed"] / d["loans"]).round(0))
        .sort_values("disbursed", ascending=False)
        .reset_index(drop=True)
    )
    by_product = (
        pd.DataFrame({"product": product, "disbursed": amount, "loans": 1})
        .groupby("product", as_index=False)
        .agg(disbursed=("disbursed", "sum"), loans=("loans", "count"))
        .sort_values("disbursed", ascending=False)
        .reset_index(drop=True)
    )
    sheets = {
        "By Branch": _with_total(by_branch, "branch"),
        "By Product": _with_total(by_product, "product"),
    }
    if date_col is not None:
        dates = pd.to_datetime(df[date_col], errors="coerce")
        trend = (
            pd.DataFrame({"date": dates.dt.date.astype(str), "disbursed": amount, "loans": 1})
            .groupby("date", as_index=False)
            .agg(disbursed=("disbursed", "sum"), loans=("loans", "count"))
            .sort_values("date")
            .reset_index(drop=True)
        )
        sheets["Daily Trend"] = trend
    else:
        notes.append("no date column found — daily trend sheet skipped")

    kpis = [
        ("Total disbursed", _rs(float(amount.sum()))),
        ("Loans", f"{len(df):,}"),
        ("Average ticket", _rs(float(amount.mean()) if len(df) else 0.0)),
        ("Top branch", str(by_branch.iloc[0]["branch"]) if len(by_branch) else "—"),
    ]
    return TemplateResult(
        "daily_disbursement", TEMPLATES["daily_disbursement"].title, kpis, sheets, notes
    )


def _collection_dpd(df: pd.DataFrame) -> TemplateResult:
    dpd_col = _find(df, ("dpd", "past_due", "overdue_days"))
    if dpd_col is None:
        raise TemplateError(
            "This template needs a DPD column (e.g. 'current_dpd' or 'days_past_due'). "
            "Please upload the collections/portfolio export that carries DPD."
        )
    dpd = _num(df, dpd_col).astype(int)
    outstanding = _num(df, _find(df, ("outstanding", "balance", "pos")))
    branch = _text(df, _find(df, ("branch", "city", "region")), "(all)")
    due = _num(df, _find(df, ("emi_due", "amount_due", "demand")))
    paid = _num(df, _find(df, ("emi_paid", "amount_paid", "collected")))
    notes: list[str] = []

    bucket = _bucket(dpd)
    buckets = (
        pd.DataFrame({"branch": branch, "bucket": bucket, "outstanding": outstanding, "loans": 1})
        .pivot_table(index="branch", columns="bucket", values="loans", aggfunc="sum", fill_value=0)
        .reindex(columns=[label for _limit, label in DPD_BUCKETS], fill_value=0)
        .reset_index()
    )
    overdue_mask = dpd > 0
    worst = (
        df.loc[overdue_mask]
        .assign(_dpd=dpd[overdue_mask])
        .sort_values("_dpd", ascending=False)
        .drop(columns="_dpd")
        .head(50)
        .reset_index(drop=True)
    )
    sheets = {"DPD Buckets": _with_total(buckets, "branch"), "Worst 50 Accounts": worst}

    total_pos = float(outstanding.sum())
    par30 = float(outstanding[dpd > 30].sum()) / total_pos * 100 if total_pos else 0.0
    par90 = float(outstanding[dpd > 90].sum()) / total_pos * 100 if total_pos else 0.0
    kpis = [
        ("Overdue accounts", f"{int(overdue_mask.sum()):,}"),
        ("PAR 30", f"{par30:.1f}%"),
        ("PAR 90", f"{par90:.1f}%"),
    ]
    if float(due.sum()) > 0:
        efficiency = float(paid.sum()) / float(due.sum()) * 100
        kpis.append(("Collection efficiency", f"{efficiency:.1f}%"))
        by_branch_eff = (
            pd.DataFrame({"branch": branch, "due": due, "paid": paid})
            .groupby("branch", as_index=False)
            .sum()
            .assign(
                efficiency_pct=lambda d: (100 * d["paid"] / d["due"].replace(0, np.nan)).round(1)
            )
            .fillna({"efficiency_pct": 0})
            .sort_values("efficiency_pct")
            .reset_index(drop=True)
        )
        sheets["Collection Efficiency"] = _with_total(by_branch_eff, "branch")
    else:
        notes.append("no EMI due/paid columns — collection-efficiency sheet skipped")
    if total_pos == 0:
        notes.append("no outstanding column — PAR ratios computed as 0")
    return TemplateResult("collection_dpd", TEMPLATES["collection_dpd"].title, kpis, sheets, notes)


def _portfolio_health(df: pd.DataFrame) -> TemplateResult:
    out_col = _find(df, ("outstanding", "balance", "pos", "loan_amount", "principal"))
    if out_col is None:
        raise TemplateError(
            "This template needs an outstanding (or loan amount) column. "
            "Please upload the active portfolio export from your LMS."
        )
    outstanding = _num(df, out_col)
    dpd = _num(df, _find(df, ("dpd", "past_due"))).astype(int)
    branch = _text(df, _find(df, ("branch", "city", "region")), "(all)")
    product = _text(df, _find(df, ("product", "scheme", "loan_type")), "(all)")
    name = _text(df, _find(df, ("customer_name", "name", "borrower")), "(unknown)")
    id_col = _find(df, ("loan_id", "account", "id"))
    notes: list[str] = []

    total_pos = float(outstanding.sum())

    def concentration(labels: pd.Series, label_name: str) -> pd.DataFrame:
        table = (
            pd.DataFrame({label_name: labels, "outstanding": outstanding, "loans": 1})
            .groupby(label_name, as_index=False)
            .agg(outstanding=("outstanding", "sum"), loans=("loans", "count"))
            .assign(
                share_pct=lambda d: (
                    (100 * d["outstanding"] / total_pos).round(1) if total_pos else 0.0
                )
            )
            .sort_values("outstanding", ascending=False)
            .reset_index(drop=True)
        )
        return _with_total(table, label_name)

    top = (
        pd.DataFrame(
            {
                "loan_id": _text(df, id_col, "—"),
                "customer": name,
                "branch": branch,
                "outstanding": outstanding,
                "dpd": dpd,
            }
        )
        .sort_values("outstanding", ascending=False)
        .head(20)
        .reset_index(drop=True)
    )

    sheets = {
        "By Branch": concentration(branch, "branch"),
        "By Product": concentration(product, "product"),
        "Top 20 Exposures": top,
    }
    par30 = float(outstanding[dpd > 30].sum()) / total_pos * 100 if total_pos else 0.0
    kpis = [
        ("Book size", _rs(total_pos)),
        ("Active accounts", f"{len(df):,}"),
        ("PAR 30", f"{par30:.1f}%"),
        ("Avg exposure", _rs(total_pos / len(df) if len(df) else 0.0)),
    ]
    if (dpd == 0).all():
        notes.append("no DPD column found — PAR shown as 0")
    return TemplateResult(
        "portfolio_health", TEMPLATES["portfolio_health"].title, kpis, sheets, notes
    )


_RUNNERS = {
    "daily_disbursement": _daily_disbursement,
    "collection_dpd": _collection_dpd,
    "portfolio_health": _portfolio_health,
}


def run_template(key: str, frame: pd.DataFrame) -> TemplateResult:
    """Apply one of the three lending templates to a raw dataset."""
    if key not in _RUNNERS:
        raise ValueError(f"unknown template: {key}")
    if frame is None or frame.empty:
        raise TemplateError("The uploaded file has no rows — please check the export.")
    return _RUNNERS[key](frame.copy())


def export_template(result: TemplateResult, path: str | Path) -> Path:
    """Write the CEO-ready workbook: Summary sheet + every template sheet."""
    out = Path(path)
    summary = pd.DataFrame(
        {
            "metric": [label for label, _v in result.kpis] + ["Notes"],
            "value": [value for _l, value in result.kpis] + ["; ".join(result.notes) or "—"],
        }
    )
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        write_formatted_sheet(writer, summary, "Summary", title=result.title)
        for sheet_name, frame in result.sheets.items():
            write_formatted_sheet(writer, frame, sheet_name, title=sheet_name)
    return out
