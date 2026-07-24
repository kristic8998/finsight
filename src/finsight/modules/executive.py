"""Executive Command Center service.

Turns the LendingDataService read-model into what a CEO actually reads:
a Business Health Score, headline KPIs, branch ranking, and a rule-based
insights engine that produces plain-English findings + recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from ..core.config import ExecutiveConfig
from ..data.queries import Kpis, LendingDataService


@dataclass
class Insight:
    severity: str  # good | watch | alert
    title: str
    detail: str
    recommendation: str


@dataclass
class HealthScore:
    score: float  # 0-100
    grade: str  # A+ .. D
    components: dict[str, float] = field(default_factory=dict)


@dataclass
class ExecutiveBrief:
    as_of: str
    kpis: Kpis
    health: HealthScore
    branches: pd.DataFrame
    dpd: pd.DataFrame
    product_mix: pd.DataFrame
    insights: list[Insight]
    summary_text: str


def _grade(score: float) -> str:
    for threshold, grade in ((90, "A+"), (80, "A"), (70, "B"), (60, "C")):
        if score >= threshold:
            return grade
    return "D"


class ExecutiveService:
    """Builds the daily executive brief."""

    def __init__(self, data: LendingDataService, config: ExecutiveConfig) -> None:
        self._data = data
        self._config = config

    def health_score(self, kpis: Kpis) -> HealthScore:
        """Weighted blend of the four numbers a lending CEO watches.

        efficiency (35%) + portfolio quality via PAR (35%) +
        target achievement (15%) + growth (15%), each normalised 0-100.
        """
        efficiency = min(kpis.efficiency_mtd, 110.0) / 110.0 * 100
        quality = max(0.0, 100.0 - kpis.par_pct * 8)  # PAR 12.5% → 0
        achievement = min(kpis.target_achievement, 120.0) / 120.0 * 100
        growth = max(0.0, min(50.0, kpis.growth_mom_pct + 25.0)) / 50.0 * 100

        components = {
            "collection_efficiency": round(efficiency, 1),
            "portfolio_quality": round(quality, 1),
            "target_achievement": round(achievement, 1),
            "growth": round(growth, 1),
        }
        score = round(0.35 * efficiency + 0.35 * quality + 0.15 * achievement + 0.15 * growth, 1)
        return HealthScore(score=score, grade=_grade(score), components=components)

    def insights(self, kpis: Kpis, branches: pd.DataFrame, mix: pd.DataFrame) -> list[Insight]:
        findings: list[Insight] = []
        cfg = self._config

        if kpis.par_pct > cfg.par_alert_pct:
            worst = branches.sort_values("overdue", ascending=False).head(3)
            names = ", ".join(worst["branch"].tolist())
            findings.append(
                Insight(
                    "alert",
                    f"Portfolio at risk is {kpis.par_pct:.1f}% (limit {cfg.par_alert_pct:.0f}%)",
                    f"Overdue ₹{kpis.overdue_amount:,.0f}. Highest exposure: {names}.",
                    "Run focused collection drives in the top-3 overdue branches this week; "
                    "review their 90+ bucket case by case.",
                )
            )
        if kpis.efficiency_mtd < cfg.efficiency_alert_pct and kpis.due_mtd > 0:
            findings.append(
                Insight(
                    "alert",
                    f"Collection efficiency {kpis.efficiency_mtd:.1f}% is below "
                    f"{cfg.efficiency_alert_pct:.0f}%",
                    f"Collected ₹{kpis.collected_mtd:,.0f} of ₹{kpis.due_mtd:,.0f} due this month.",
                    "Prioritise NACH re-presentation and day-5 calling for bounced EMIs.",
                )
            )
        if not mix.empty and float(mix["share_pct"].iloc[0]) > cfg.concentration_alert_pct:
            top = mix.iloc[0]
            findings.append(
                Insight(
                    "watch",
                    f"Concentration: {top['product']} is {top['share_pct']:.0f}% of the book",
                    "A single-product shock would hit most of the portfolio.",
                    f"Cap incremental {top['product']} share and push diversification targets "
                    "to branch heads.",
                )
            )
        if kpis.growth_mom_pct < 0:
            findings.append(
                Insight(
                    "watch",
                    f"Disbursement fell {abs(kpis.growth_mom_pct):.1f}% month-on-month",
                    f"MTD disbursement ₹{kpis.disbursed_mtd:,.0f}.",
                    "Check sourcing funnel and sanction TAT; compare branch-level pipelines.",
                )
            )
        if len(branches) >= 2:
            spread = float(branches["efficiency_pct"].max() - branches["efficiency_pct"].min())
            if spread > 15:
                best, worst = branches.iloc[0], branches.iloc[-1]
                findings.append(
                    Insight(
                        "watch",
                        f"Wide branch performance spread ({spread:.0f} pts of efficiency)",
                        f"{best['branch']} leads at {best['efficiency_pct']:.0f}%; "
                        f"{worst['branch']} trails at {worst['efficiency_pct']:.0f}%.",
                        f"Pair {worst['branch']} with {best['branch']}'s playbook; "
                        "set a 2-week improvement checkpoint.",
                    )
                )
        if kpis.target_achievement >= 100:
            findings.append(
                Insight(
                    "good",
                    f"Monthly target achieved ({kpis.target_achievement:.0f}%)",
                    f"Collections ₹{kpis.collected_mtd:,.0f} vs target ₹{kpis.target_mtd:,.0f}.",
                    "Recognise top officers publicly — momentum is a collections asset.",
                )
            )
        if not findings:
            findings.append(
                Insight(
                    "good",
                    "No red flags today",
                    "All monitored indicators are within configured thresholds.",
                    "Keep thresholds under quarterly review so 'green' stays meaningful.",
                )
            )
        return findings

    def brief(self, as_of: date | None = None) -> ExecutiveBrief:
        """One call = the full CEO morning pack."""
        kpis = self._data.kpis(as_of)
        branches = self._data.branch_summary(as_of)
        dpd = self._data.dpd_buckets(as_of)
        mix = self._data.product_mix()
        health = self.health_score(kpis)
        insights = self.insights(kpis, branches, mix)

        alerts = sum(1 for i in insights if i.severity == "alert")
        top_branch = branches.iloc[0]["branch"] if len(branches) else "-"
        summary = (
            f"Business health {health.score:.0f}/100 ({health.grade}). "
            f"Portfolio ₹{kpis.portfolio_outstanding:,.0f} across {kpis.active_loans} active "
            f"loans. MTD collections ₹{kpis.collected_mtd:,.0f} "
            f"({kpis.efficiency_mtd:.0f}% of dues, {kpis.target_achievement:.0f}% of target). "
            f"PAR {kpis.par_pct:.1f}% with ₹{kpis.overdue_amount:,.0f} overdue. "
            f"Best branch: {top_branch}. "
            + (f"{alerts} item(s) need attention today." if alerts else "No alerts today.")
        )
        return ExecutiveBrief(
            as_of=(as_of or date.today()).isoformat(),
            kpis=kpis,
            health=health,
            branches=branches,
            dpd=dpd,
            product_mix=mix,
            insights=insights,
            summary_text=summary,
        )
