"""LendingDataService — every KPI and frame the modules need, in one place.

All portfolio math lives here (not in the UI, not in five different
Excel sheets): outstanding, dues vs collections, efficiency, PAR/DPD,
NPA, growth, rankings, productivity, and daily series. Each method
returns plain DataFrames/dataclasses so Executive, MIS, Analytics, and
NLQ all agree on the numbers — one source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from .connections import ConnectionManager

_DPD_BUCKETS = ((1, 30, "1-30"), (31, 60, "31-60"), (61, 90, "61-90"), (91, 10_000, "90+"))


@dataclass
class Kpis:
    """Headline numbers for a period (defaults: current month-to-date)."""

    portfolio_outstanding: float
    active_loans: int
    npa_loans: int
    npa_amount: float
    disbursed_mtd: float
    due_mtd: float
    collected_mtd: float
    efficiency_mtd: float  # collected / due, %
    target_mtd: float
    target_achievement: float  # collected / target, %
    overdue_amount: float
    par_pct: float  # overdue principal proxy / outstanding, %
    interest_collected_mtd: float
    growth_mom_pct: float  # disbursement growth vs previous month


class LendingDataService:
    """Read-model over the canonical lending schema."""

    def __init__(self, connections: ConnectionManager, connection_name: str) -> None:
        self._cm = connections
        self._name = connection_name

    # ---- low-level helpers -------------------------------------------------
    def _frame(self, sql: str) -> pd.DataFrame:
        return self._cm.run_query(self._name, sql).frame

    @staticmethod
    def _month_key(day: date) -> str:
        return day.strftime("%Y-%m")

    # ---- core frames ---------------------------------------------------------
    def loans(self) -> pd.DataFrame:
        return self._frame(
            "SELECT l.*, b.name AS branch, b.region FROM loans l"
            " JOIN branches b ON b.id = l.branch_id"
        )

    def payments_status(self, as_of: date | None = None) -> pd.DataFrame:
        """Payment rows enriched with dpd + outstanding per installment."""
        today = as_of or date.today()
        frame = self._frame(
            "SELECT p.*, l.branch_id, b.name AS branch, l.product, l.status"
            " FROM payments p JOIN loans l ON l.id = p.loan_id"
            " JOIN branches b ON b.id = l.branch_id"
        )
        frame["due_date"] = pd.to_datetime(frame["due_date"]).dt.date
        frame["unpaid"] = (frame["amount_due"] - frame["amount_paid"]).clip(lower=0)
        overdue_mask = (frame["due_date"] < today) & (frame["unpaid"] > 0.005)
        frame["dpd"] = 0
        frame.loc[overdue_mask, "dpd"] = [
            (today - d).days for d in frame.loc[overdue_mask, "due_date"]
        ]
        return frame

    # ---- KPIs -----------------------------------------------------------------
    def kpis(self, as_of: date | None = None) -> Kpis:
        today = as_of or date.today()
        month = self._month_key(today)
        prev_month = self._month_key(today.replace(day=1) - timedelta(days=1))

        loans = self.loans()
        pays = self.payments_status(today)
        past = pays[pd.to_datetime(pays["due_date"]).dt.date <= today]

        paid_per_loan = past.groupby("loan_id")["amount_paid"].sum()
        principal = loans.set_index("id")["principal"]
        # Outstanding proxy: principal minus principal-share of what's paid.
        rate_factor = 1 + loans.set_index("id")["interest_rate"] / 100 * (
            loans.set_index("id")["tenure_months"] / 12
        )
        principal_paid = (paid_per_loan / rate_factor).reindex(principal.index).fillna(0)
        outstanding_per_loan = (principal - principal_paid).clip(lower=0)
        open_ids = loans[loans["status"] != "closed"]["id"]
        portfolio = float(outstanding_per_loan.loc[open_ids].sum())

        month_mask = past["due_date"].map(lambda d: d.strftime("%Y-%m")) == month
        due_mtd = float(past.loc[month_mask, "amount_due"].sum())
        collected_mtd = float(
            past[past["paid_date"].notna()]
            .loc[lambda f: pd.to_datetime(f["paid_date"]).dt.strftime("%Y-%m") == month][
                "amount_paid"
            ]
            .sum()
        )
        targets = self._frame(
            f"SELECT COALESCE(SUM(target_amount),0) AS t FROM collection_targets"
            f" WHERE month = '{month}'"
        )
        target_mtd = float(targets["t"].iloc[0])

        overdue_amount = float(past.loc[past["dpd"] > 0, "unpaid"].sum())
        npa = loans[loans["status"] == "npa"]
        npa_amount = float(outstanding_per_loan.loc[npa["id"]].sum())

        loans["disb_month"] = pd.to_datetime(loans["disbursed_on"]).dt.strftime("%Y-%m")
        disbursed_mtd = float(loans.loc[loans["disb_month"] == month, "principal"].sum())
        disbursed_prev = float(loans.loc[loans["disb_month"] == prev_month, "principal"].sum())

        interest_share = past[past["paid_date"].notna()].copy()
        month_paid_mask = pd.to_datetime(interest_share["paid_date"]).dt.strftime("%Y-%m") == month
        # Interest share of an EMI ≈ 1 - principal_factor; use portfolio-level factor.
        mean_factor = float(rate_factor.mean()) if len(rate_factor) else 1.0
        interest_collected = float(
            interest_share.loc[month_paid_mask, "amount_paid"].sum() * (1 - 1 / mean_factor)
        )

        return Kpis(
            portfolio_outstanding=round(portfolio, 2),
            active_loans=int((loans["status"] == "active").sum()),
            npa_loans=int(len(npa)),
            npa_amount=round(npa_amount, 2),
            disbursed_mtd=round(disbursed_mtd, 2),
            due_mtd=round(due_mtd, 2),
            collected_mtd=round(collected_mtd, 2),
            efficiency_mtd=round(collected_mtd / due_mtd * 100, 1) if due_mtd else 0.0,
            target_mtd=round(target_mtd, 2),
            target_achievement=round(collected_mtd / target_mtd * 100, 1) if target_mtd else 0.0,
            overdue_amount=round(overdue_amount, 2),
            par_pct=round(overdue_amount / portfolio * 100, 2) if portfolio else 0.0,
            interest_collected_mtd=round(interest_collected, 2),
            growth_mom_pct=(
                round((disbursed_mtd - disbursed_prev) / disbursed_prev * 100, 1)
                if disbursed_prev
                else 0.0
            ),
        )

    # ---- breakdowns -----------------------------------------------------------
    def branch_summary(self, as_of: date | None = None) -> pd.DataFrame:
        """Per-branch dues, collections, efficiency, overdue, and rank score."""
        today = as_of or date.today()
        month = self._month_key(today)
        pays = self.payments_status(today)
        past = pays[pd.to_datetime(pays["due_date"]).dt.date <= today]

        month_rows = past[past["due_date"].map(lambda d: d.strftime("%Y-%m")) == month]
        due = month_rows.groupby("branch")["amount_due"].sum()
        collected = (
            past[past["paid_date"].notna()]
            .loc[lambda f: pd.to_datetime(f["paid_date"]).dt.strftime("%Y-%m") == month]
            .groupby("branch")["amount_paid"]
            .sum()
        )
        overdue = past[past["dpd"] > 0].groupby("branch")["unpaid"].sum()

        summary = pd.DataFrame({"due_mtd": due}).fillna(0.0)
        summary["collected_mtd"] = collected.reindex(summary.index).fillna(0.0)
        summary["overdue"] = overdue.reindex(summary.index).fillna(0.0)
        summary["efficiency_pct"] = (
            (summary["collected_mtd"] / summary["due_mtd"].replace(0, pd.NA) * 100)
            .astype(float)
            .fillna(0.0)
            .round(1)
        )
        exposure = summary["due_mtd"] + summary["overdue"]
        summary["overdue_pct"] = (
            (summary["overdue"] / exposure.replace(0, pd.NA) * 100)
            .astype(float)
            .fillna(0.0)
            .round(1)
        )
        summary["score"] = (
            0.6 * summary["efficiency_pct"] + 0.4 * (100 - summary["overdue_pct"])
        ).round(1)
        summary = summary.sort_values("score", ascending=False).reset_index()
        summary.insert(0, "rank", range(1, len(summary) + 1))
        return summary.round(2)

    def dpd_buckets(self, as_of: date | None = None) -> pd.DataFrame:
        pays = self.payments_status(as_of)
        overdue = pays[pays["dpd"] > 0]
        rows = []
        for low, high, label in _DPD_BUCKETS:
            mask = (overdue["dpd"] >= low) & (overdue["dpd"] <= high)
            rows.append(
                {
                    "bucket": label,
                    "installments": int(mask.sum()),
                    "amount": round(float(overdue.loc[mask, "unpaid"].sum()), 2),
                }
            )
        return pd.DataFrame(rows)

    def product_mix(self) -> pd.DataFrame:
        loans = self.loans()
        active = loans[loans["status"] != "closed"]
        mix = active.groupby("product")["principal"].agg(["count", "sum"]).reset_index()
        mix.columns = ["product", "loans", "principal"]
        total = mix["principal"].sum()
        mix["share_pct"] = (mix["principal"] / total * 100).round(1) if total else 0.0
        return mix.sort_values("principal", ascending=False).reset_index(drop=True)

    def daily_collections(self, days: int = 90, as_of: date | None = None) -> pd.DataFrame:
        """Collections per day for trend charts and forecasting."""
        today = as_of or date.today()
        start = today - timedelta(days=days)
        pays = self.payments_status(today)
        paid = pays[pays["paid_date"].notna()].copy()
        paid["paid_on"] = pd.to_datetime(paid["paid_date"]).dt.date
        window = paid[(paid["paid_on"] >= start) & (paid["paid_on"] <= today)]
        series = window.groupby("paid_on")["amount_paid"].sum()
        index = pd.date_range(start, today, freq="D").date
        return pd.DataFrame(
            {"date": index, "collected": [round(float(series.get(d, 0.0)), 2) for d in index]}
        )

    def officer_productivity(self, as_of: date | None = None) -> pd.DataFrame:
        today = as_of or date.today()
        month = self._month_key(today)
        frame = self._frame(
            "SELECT o.name AS officer, b.name AS branch, o.role,"
            " COALESCE(SUM(p.amount_paid),0) AS collected, COUNT(DISTINCT l.id) AS loans"
            " FROM officers o"
            " JOIN branches b ON b.id = o.branch_id"
            " LEFT JOIN loans l ON l.officer_id = o.id"
            " LEFT JOIN payments p ON p.loan_id = l.id"
            f"  AND substr(COALESCE(p.paid_date,''),1,7) = '{month}'"
            " GROUP BY o.id ORDER BY collected DESC"
        )
        return frame.round(2)

    def overdue_loans(self, branch: str | None = None, limit: int = 200) -> pd.DataFrame:
        pays = self.payments_status()
        overdue = pays[pays["dpd"] > 0]
        if branch:
            overdue = overdue[overdue["branch"].str.lower() == branch.lower()]
        grouped = (
            overdue.groupby(["loan_id", "branch", "product"])
            .agg(
                overdue_amount=("unpaid", "sum"),
                max_dpd=("dpd", "max"),
                installments=("id", "count"),
            )
            .reset_index()
            .sort_values("overdue_amount", ascending=False)
            .head(limit)
        )
        return grouped.round(2)
