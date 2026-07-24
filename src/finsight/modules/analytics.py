"""AI Analytics: forecasting, anomaly detection, segmentation, risk scoring.

Deliberately transparent techniques — linear trend + weekday seasonality
for forecasts, robust z-scores for anomalies, KMeans for segments, and a
logistic model for loan risk — because in lending you must be able to
explain every number to an auditor. Each result carries its own
plain-English explanation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.preprocessing import StandardScaler

from ..data.queries import LendingDataService


@dataclass
class Forecast:
    history: pd.DataFrame  # date, collected
    forecast: pd.DataFrame  # date, predicted
    expected_total: float
    explanation: str


@dataclass
class Anomalies:
    frame: pd.DataFrame  # date, collected, zscore
    explanation: str


@dataclass
class Segmentation:
    frame: pd.DataFrame  # loan_id, features..., segment
    profile: pd.DataFrame  # per-segment means + label
    explanation: str


@dataclass
class RiskScores:
    frame: pd.DataFrame  # loan_id, branch, features..., risk_score
    auc_like: float
    explanation: str
    top_factors: list[str] = field(default_factory=list)


class AnalyticsService:
    """Analytics over the lending read-model."""

    def __init__(self, data: LendingDataService) -> None:
        self._data = data

    # ---- forecasting -------------------------------------------------------
    def collections_forecast(self, history_days: int = 90, horizon_days: int = 30) -> Forecast:
        history = self._data.daily_collections(days=history_days)
        series = history["collected"].to_numpy(dtype=float)
        days = np.arange(len(series), dtype=float).reshape(-1, 1)

        model = LinearRegression()
        model.fit(days, series)
        trend = model.predict(days)

        # Weekday seasonality: mean multiplicative factor per weekday.
        weekdays = pd.to_datetime(history["date"]).dt.weekday.to_numpy()
        factors = np.ones(7)
        for wd in range(7):
            mask = weekdays == wd
            if mask.any() and trend[mask].mean() > 0:
                factors[wd] = float(np.clip(series[mask].mean() / trend[mask].mean(), 0.3, 2.0))

        last_day = history["date"].iloc[-1]
        future_dates = [last_day + timedelta(days=i) for i in range(1, horizon_days + 1)]
        future_x = np.arange(len(series), len(series) + horizon_days, dtype=float).reshape(-1, 1)
        base = model.predict(future_x)
        predicted = np.maximum(0.0, base * np.array([factors[d.weekday()] for d in future_dates]))
        forecast = pd.DataFrame({"date": future_dates, "predicted": np.round(predicted, 2)})

        slope_per_day = float(model.coef_[0])
        direction = "rising" if slope_per_day > 0 else "falling"
        return Forecast(
            history=history,
            forecast=forecast,
            expected_total=round(float(predicted.sum()), 2),
            explanation=(
                f"Linear trend over the last {history_days} days ({direction} "
                f"{abs(slope_per_day):,.0f}/day) with weekday seasonality factors. "
                f"Expected next-{horizon_days}-day collections: {predicted.sum():,.0f}."
            ),
        )

    # ---- anomaly detection ------------------------------------------------------
    def collection_anomalies(self, days: int = 90, z_threshold: float = 2.5) -> Anomalies:
        history = self._data.daily_collections(days=days)
        values = history["collected"].to_numpy(dtype=float)
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median))) or 1.0
        robust_z = 0.6745 * (values - median) / mad  # standard MAD z-score
        history = history.assign(zscore=np.round(robust_z, 2))
        flagged = history[np.abs(history["zscore"]) >= z_threshold].reset_index(drop=True)
        return Anomalies(
            frame=flagged,
            explanation=(
                f"Robust z-score (median/MAD) over {days} days; |z| ≥ {z_threshold} flags "
                f"{len(flagged)} unusual day(s). MAD-based scoring resists being skewed by "
                "the anomalies themselves."
            ),
        )

    # ---- segmentation ------------------------------------------------------------
    def customer_segments(self, k: int = 4, random_state: int = 42) -> Segmentation:
        pays = self._data.payments_status()
        past = pays[pd.to_datetime(pays["due_date"]).dt.date <= date.today()]
        per_loan = past.groupby("loan_id").agg(
            outstanding=("unpaid", "sum"),
            max_dpd=("dpd", "max"),
            installments=("id", "count"),
            paid_ratio=("amount_paid", lambda s: float(s.sum())),
        )
        due_total = past.groupby("loan_id")["amount_due"].sum()
        per_loan["paid_ratio"] = (
            (per_loan["paid_ratio"] / due_total.replace(0, np.nan)).fillna(0.0).clip(0, 1.5)
        )
        per_loan = per_loan.dropna()
        if len(per_loan) < k:
            raise ValueError(f"need at least {k} loans to build {k} segments")

        features = per_loan[["outstanding", "max_dpd", "paid_ratio"]]
        scaled = StandardScaler().fit_transform(features)
        km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        per_loan = per_loan.assign(segment=km.fit_predict(scaled))

        profile = (
            per_loan.groupby("segment")
            .agg(
                loans=("segment", "count"),
                avg_outstanding=("outstanding", "mean"),
                avg_dpd=("max_dpd", "mean"),
                avg_paid_ratio=("paid_ratio", "mean"),
            )
            .round(2)
        )

        def label(row: pd.Series) -> str:
            if row["avg_dpd"] >= 60:
                return "High Risk / Deep Delinquent"
            if row["avg_dpd"] >= 15:
                return "Watchlist / Irregular Payers"
            if row["avg_paid_ratio"] >= 0.95:
                return "Prime / On-time Payers"
            return "Stable / Minor Slippage"

        profile["label"] = profile.apply(label, axis=1)
        per_loan = per_loan.merge(
            profile[["label"]], left_on="segment", right_index=True
        ).reset_index()
        return Segmentation(
            frame=per_loan.round(2),
            profile=profile.reset_index(),
            explanation=(
                f"KMeans (k={k}) on outstanding, worst DPD, and paid ratio "
                "(standardised). Labels are assigned from segment behaviour so "
                "business users read segments, not cluster ids."
            ),
        )

    # ---- risk scoring ---------------------------------------------------------
    def loan_risk_scores(self, random_state: int = 42) -> RiskScores:
        """Probability-of-stress score per active loan.

        Trains a logistic regression where current NPA status is the
        label and repayment behaviour features are the inputs, then
        scores the active book. On the demo data this is a teaching
        model; point it at your real book and retrain before use.
        """
        pays = self._data.payments_status()
        past = pays[pd.to_datetime(pays["due_date"]).dt.date <= date.today()]
        loans = self._data.loans().set_index("id")

        grouped = past.groupby("loan_id")
        features = pd.DataFrame(
            {
                "late_ratio": grouped.apply(
                    lambda g: float(((g["dpd"] > 0) | (g["paid_date"].isna())).mean()),
                    include_groups=False,
                ),
                "avg_dpd": grouped["dpd"].mean(),
                "max_dpd": grouped["dpd"].max(),
                "unpaid_ratio": grouped.apply(
                    lambda g: float(g["unpaid"].sum() / max(g["amount_due"].sum(), 1.0)),
                    include_groups=False,
                ),
            }
        ).fillna(0.0)
        features["ticket"] = loans["principal"].reindex(features.index).fillna(0.0) / 100_000
        labels = (loans["status"].reindex(features.index) == "npa").astype(int)

        if labels.nunique() < 2:
            raise ValueError("risk model needs both NPA and non-NPA loans to train")

        scaler = StandardScaler()
        x = scaler.fit_transform(features)
        model = LogisticRegression(max_iter=500, random_state=random_state)
        model.fit(x, labels)
        probability = model.predict_proba(x)[:, 1]

        # Simple separation measure (mean score gap), honest and explainable.
        gap = float(probability[labels == 1].mean() - probability[labels == 0].mean())

        coefs = sorted(
            zip(features.columns, model.coef_[0], strict=True),
            key=lambda pair: abs(pair[1]),
            reverse=True,
        )
        top_factors = [f"{name} ({'+' if c > 0 else '-'})" for name, c in coefs[:3]]

        scored = features.assign(
            risk_score=np.round(probability * 100, 1),
            status=loans["status"].reindex(features.index),
            branch=loans["branch"].reindex(features.index),
        ).reset_index()
        scored = (
            scored[scored["status"] != "closed"]
            .sort_values("risk_score", ascending=False)
            .reset_index(drop=True)
        )

        return RiskScores(
            frame=scored.round(3),
            auc_like=round(gap, 3),
            explanation=(
                "Logistic regression on repayment behaviour (late ratio, DPD, unpaid "
                "ratio, ticket size); score = probability of stress ×100. Trained on "
                "the current book's NPA labels — retrain on real data before decisions."
            ),
            top_factors=top_factors,
        )
