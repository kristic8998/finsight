"""Natural-language query engine (pattern-based, fully offline).

Understands the questions a lending analyst actually asks every day and
compiles them to SQL over the canonical schema — no cloud LLM, no data
leaves the laptop, and the generated SQL is always shown for
transparency. Unrecognised questions return suggestions instead of
guesses: in finance, a wrong confident answer is worse than none.

Supported intents (case-insensitive):
    "top 5 branches by overdue" / "worst branches by collections"
    "branches with highest overdue|collections|efficiency|npa|portfolio"
    "collections trend last 60 days" / "disbursement trend last 6 months"
    "overdue loans in <branch>" / "list npa loans"
    "collection efficiency by branch"
    "product mix" / "portfolio by product"
    "summary" / "health" / "how is the business"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from ..data.queries import LendingDataService

_METRIC_ALIASES = {
    "overdue": "overdue",
    "over due": "overdue",
    "pending": "overdue",
    "collections": "collected_mtd",
    "collection": "collected_mtd",
    "collected": "collected_mtd",
    "efficiency": "efficiency_pct",
    "npa": "npa",
    "portfolio": "portfolio",
    "outstanding": "portfolio",
    "disbursement": "disbursed",
    "disbursed": "disbursed",
}

EXAMPLES = [
    "top 5 branches by overdue",
    "branches with highest collections",
    "collection efficiency by branch",
    "collections trend last 60 days",
    "overdue loans in Andheri",
    "list npa loans",
    "product mix",
    "business summary",
]


@dataclass
class NlqAnswer:
    question: str
    intent: str
    sql: str  # the query (or derivation) shown to the user
    frame: pd.DataFrame
    narrative: str
    chart: str = "bar"  # bar | line | table
    suggestions: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.intent != "unknown"


class NlqEngine:
    """Compiles supported English questions into data answers."""

    def __init__(self, data: LendingDataService) -> None:
        self._data = data

    def ask(self, question: str) -> NlqAnswer:
        text = " ".join(question.lower().strip().split())
        if not text:
            return self._unknown(question)

        handlers = (
            self._try_summary,
            self._try_trend,
            self._try_overdue_loans,
            self._try_npa_list,
            self._try_efficiency_by_branch,
            self._try_product_mix,
            self._try_branch_ranking,
        )
        for handler in handlers:
            answer = handler(question, text)
            if answer is not None:
                return answer
        return self._unknown(question)

    # ---- intent handlers -----------------------------------------------------
    def _try_branch_ranking(self, question: str, text: str) -> NlqAnswer | None:
        match = re.search(
            r"(top|bottom|worst|best|highest|lowest)\s*(\d+)?\s*branch(?:es)?"
            r"(?:\s+(?:by|with|in)\s+(?:the\s+)?(?:highest\s+|lowest\s+)?([a-z ]+))?",
            text,
        )
        if not match and "branch" in text:
            for alias in _METRIC_ALIASES:
                if alias in text:
                    match = re.search(r"(highest|top|worst|lowest|best)?", text)
                    metric_word = alias
                    break
            else:
                return None
            direction_word = match.group(1) if match and match.group(1) else "highest"
            n = 10
        elif match:
            direction_word = match.group(1)
            n = int(match.group(2)) if match.group(2) else 5
            metric_word = (match.group(3) or "overdue").strip()
        else:
            return None

        metric_key = next((v for k, v in _METRIC_ALIASES.items() if k in metric_word), "overdue")
        ascending = direction_word in ("bottom", "lowest") or (
            direction_word in ("worst",) and metric_key in ("collected_mtd", "efficiency_pct")
        )

        branches = self._data.branch_summary()
        column = {
            "overdue": "overdue",
            "collected_mtd": "collected_mtd",
            "efficiency_pct": "efficiency_pct",
            "npa": "overdue",
            "portfolio": "due_mtd",
            "disbursed": "due_mtd",
        }[metric_key]
        ranked = branches.sort_values(column, ascending=ascending).head(n)
        result = ranked[["branch", column]].reset_index(drop=True)

        leader = result.iloc[0]
        narrative = (
            f"{'Lowest' if ascending else 'Highest'} {column.replace('_', ' ')}: "
            f"{leader['branch']} at {leader[column]:,.0f}. Showing {len(result)} branch(es)."
        )
        return NlqAnswer(
            question=question,
            intent="branch_ranking",
            sql=(
                "-- derived from branch_summary()\n"
                f"SELECT branch, {column} FROM branch_summary "
                f"ORDER BY {column} {'ASC' if ascending else 'DESC'} LIMIT {n}"
            ),
            frame=result,
            narrative=narrative,
            chart="bar",
        )

    def _try_trend(self, question: str, text: str) -> NlqAnswer | None:
        if "trend" not in text and "last" not in text:
            return None
        if not any(word in text for word in ("collection", "collections", "disbursement")):
            return None
        match = re.search(r"last\s+(\d+)\s*(day|days|month|months)", text)
        days = 60
        if match:
            qty = int(match.group(1))
            days = qty * 30 if "month" in match.group(2) else qty
        days = max(7, min(days, 365))

        series = self._data.daily_collections(days=days)
        total = float(series["collected"].sum())
        first_half = float(series.head(len(series) // 2)["collected"].mean())
        second_half = float(series.tail(len(series) // 2)["collected"].mean())
        direction = "up" if second_half >= first_half else "down"
        narrative = (
            f"Collections over the last {days} days total {total:,.0f}; the daily average "
            f"moved {direction} from {first_half:,.0f} to {second_half:,.0f}."
        )
        return NlqAnswer(
            question=question,
            intent="trend",
            sql=(
                "SELECT paid_date, SUM(amount_paid) FROM payments "
                f"WHERE paid_date >= date('now','-{days} day') GROUP BY paid_date"
            ),
            frame=series,
            narrative=narrative,
            chart="line",
        )

    def _try_overdue_loans(self, question: str, text: str) -> NlqAnswer | None:
        if "overdue" not in text or "loan" not in text:
            return None
        branch = None
        match = re.search(r"in\s+([a-z .]+)$", text)
        if match:
            branch = match.group(1).strip()
        frame = self._data.overdue_loans(branch=branch, limit=100)
        where = f" for branch '{branch}'" if branch else ""
        narrative = f"{len(frame)} overdue loan(s){where}, worst first. " + (
            f"Top exposure loan #{int(frame.iloc[0]['loan_id'])} at "
            f"{frame.iloc[0]['overdue_amount']:,.0f}."
            if len(frame)
            else "Book is clean."
        )
        return NlqAnswer(
            question=question,
            intent="overdue_loans",
            sql="-- derived from overdue_loans(): unpaid past-due installments per loan",
            frame=frame,
            narrative=narrative,
            chart="table",
        )

    def _try_npa_list(self, question: str, text: str) -> NlqAnswer | None:
        if "npa" not in text:
            return None
        loans = self._data.loans()
        npa = loans[loans["status"] == "npa"][
            ["id", "branch", "customer_name", "product", "principal", "disbursed_on"]
        ].reset_index(drop=True)
        return NlqAnswer(
            question=question,
            intent="npa_list",
            sql="SELECT ... FROM loans WHERE status = 'npa'",
            frame=npa,
            narrative=f"{len(npa)} NPA loan(s) totalling {npa['principal'].sum():,.0f} principal.",
            chart="table",
        )

    def _try_efficiency_by_branch(self, question: str, text: str) -> NlqAnswer | None:
        if "efficiency" not in text:
            return None
        branches = self._data.branch_summary()
        frame = branches[["branch", "efficiency_pct"]].reset_index(drop=True)
        best, worst = branches.iloc[0], branches.iloc[-1]
        return NlqAnswer(
            question=question,
            intent="efficiency_by_branch",
            sql="-- derived from branch_summary(): collected_mtd / due_mtd per branch",
            frame=frame,
            narrative=(
                f"Efficiency ranges {worst['efficiency_pct']:.0f}%–{best['efficiency_pct']:.0f}%. "
                f"Leader: {best['branch']}."
            ),
            chart="bar",
        )

    def _try_product_mix(self, question: str, text: str) -> NlqAnswer | None:
        if "product" not in text and "mix" not in text:
            return None
        mix = self._data.product_mix()
        top = mix.iloc[0]
        return NlqAnswer(
            question=question,
            intent="product_mix",
            sql="SELECT product, COUNT(*), SUM(principal) FROM loans GROUP BY product",
            frame=mix,
            narrative=(
                f"{top['product']} leads the book at {top['share_pct']:.0f}% "
                f"of open principal across {int(top['loans'])} loans."
            ),
            chart="bar",
        )

    def _try_summary(self, question: str, text: str) -> NlqAnswer | None:
        if not any(w in text for w in ("summary", "health", "how is", "overview")):
            return None
        kpis = self._data.kpis()
        frame = pd.DataFrame(
            {
                "metric": [
                    "portfolio",
                    "active_loans",
                    "collected_mtd",
                    "efficiency_%",
                    "overdue",
                    "PAR_%",
                    "NPA_loans",
                    "growth_MoM_%",
                ],
                "value": [
                    kpis.portfolio_outstanding,
                    kpis.active_loans,
                    kpis.collected_mtd,
                    kpis.efficiency_mtd,
                    kpis.overdue_amount,
                    kpis.par_pct,
                    kpis.npa_loans,
                    kpis.growth_mom_pct,
                ],
            }
        )
        narrative = (
            f"Portfolio {kpis.portfolio_outstanding:,.0f} • collections MTD "
            f"{kpis.collected_mtd:,.0f} ({kpis.efficiency_mtd:.0f}% efficiency) • "
            f"PAR {kpis.par_pct:.1f}% • {kpis.npa_loans} NPAs."
        )
        return NlqAnswer(
            question=question,
            intent="summary",
            sql="-- derived from kpis()",
            frame=frame,
            narrative=narrative,
            chart="table",
        )

    def _unknown(self, question: str) -> NlqAnswer:
        return NlqAnswer(
            question=question,
            intent="unknown",
            sql="",
            frame=pd.DataFrame(),
            narrative=(
                "I did not recognise that question, and guessing with financial data "
                "is worse than asking again. Try one of the examples."
            ),
            chart="table",
            suggestions=EXAMPLES,
        )
