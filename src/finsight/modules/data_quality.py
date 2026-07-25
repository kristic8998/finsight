"""Data Quality Center — profiling, rule checks, and anomaly detection.

Pure pandas, no UI. One accumulator drives both the in-memory path
(:func:`profile_frame`, used for SQL results and moderate files) and the
streaming path (:func:`profile_csv`, which reads a CSV in row-chunks so a
multi-million-row file never has to fit in RAM at once). Because both
paths feed the *same* accumulator, "profile a DataFrame" and "profile a
huge CSV in chunks" produce identical reports on identical data — which
the test-suite asserts directly.

The output is a :class:`DataQualityReport`: per-column profiles, a list
of rule violations / anomalies with severities, and a 0–100 quality
score, all exportable to a multi-sheet Excel exception report.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

# Column-name hints that mark a likely unique key or a monetary field.
KEY_HINTS = ("id", "utr", "ref", "txn", "transaction", "account", "email", "pan", "code")
AMOUNT_HINTS = ("amount", "amt", "value", "balance", "principal", "emi", "paid", "due")

# Memory guards for the streaming path (bound per-column state on huge data).
_DISTINCT_CAP = 100_000
_RESERVOIR_CAP = 200_000
_DUP_HASH_CAP = 3_000_000


@dataclass
class ColumnProfile:
    name: str
    dtype: str
    count: int  # non-null values
    missing: int
    missing_pct: float
    distinct: int
    distinct_pct: float
    distinct_capped: bool
    top_value: str
    top_count: int
    numeric_min: float | None
    numeric_max: float | None
    numeric_mean: float | None
    sample: list[str]


@dataclass
class Issue:
    """A rule violation or detected anomaly."""

    severity: str  # "alert" | "watch"
    rule: str
    column: str
    count: int
    detail: str


@dataclass
class DataQualityReport:
    rows: int
    columns: int
    duplicate_rows: int
    duplicate_rows_approx: bool
    score: float
    grade: str
    generated_at: str
    column_profiles: list[ColumnProfile] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    # ---- convenience views ------------------------------------------------
    def summary(self) -> str:
        alerts = sum(1 for i in self.issues if i.severity == "alert")
        watches = sum(1 for i in self.issues if i.severity == "watch")
        return (
            f"{self.rows:,} rows × {self.columns} cols · "
            f"score {self.score:.0f}/100 (grade {self.grade}) · "
            f"{alerts} alert(s), {watches} warning(s), "
            f"{self.duplicate_rows:,} duplicate row(s)"
        )

    def profiles_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "column": p.name,
                "dtype": p.dtype,
                "non_null": p.count,
                "missing": p.missing,
                "missing_%": round(p.missing_pct, 2),
                "distinct": p.distinct,
                "distinct_%": round(p.distinct_pct, 2),
                "top_value": p.top_value,
                "top_count": p.top_count,
                "min": p.numeric_min,
                "max": p.numeric_max,
                "mean": (round(p.numeric_mean, 4) if p.numeric_mean is not None else None),
                "sample": ", ".join(p.sample),
            }
            for p in self.column_profiles
        )

    def issues_frame(self) -> pd.DataFrame:
        if not self.issues:
            return pd.DataFrame(columns=["severity", "rule", "column", "count", "detail"])
        return pd.DataFrame(
            {
                "severity": i.severity,
                "rule": i.rule,
                "column": i.column,
                "count": i.count,
                "detail": i.detail,
            }
            for i in self.issues
        )


class _ColumnState:
    __slots__ = (
        "missing",
        "counts",
        "distinct_capped",
        "is_numeric",
        "n_sum",
        "n_count",
        "n_min",
        "n_max",
        "reservoir",
        "whitespace",
        "dtype",
    )

    def __init__(self) -> None:
        self.missing = 0
        self.counts: Counter = Counter()
        self.distinct_capped = False
        self.is_numeric: bool | None = None
        self.n_sum = 0.0
        self.n_count = 0
        self.n_min: float | None = None
        self.n_max: float | None = None
        self.reservoir: list[float] = []
        self.whitespace = 0
        self.dtype = ""


class _Accumulator:
    """Streaming profiler state; fed one or many chunks, then finalized."""

    def __init__(self, *, missing_alert_pct: float = 20.0) -> None:
        self.missing_alert_pct = missing_alert_pct
        self.rows = 0
        self.columns: list[str] = []
        self._state: dict[str, _ColumnState] = {}
        self._seen_hashes: set[int] = set()
        self.duplicate_rows = 0
        self.duplicate_rows_approx = False

    # ---- ingest -----------------------------------------------------------
    def update(self, chunk: pd.DataFrame) -> None:
        if chunk.empty and self.columns:
            return
        if not self.columns:
            self.columns = [str(c) for c in chunk.columns]
            for name in self.columns:
                self._state[name] = _ColumnState()
        self.rows += len(chunk)
        self._update_duplicates(chunk)
        for name in self.columns:
            if name not in chunk.columns:
                continue
            self._update_column(self._state[name], chunk[name])

    def _update_duplicates(self, chunk: pd.DataFrame) -> None:
        if chunk.shape[0] == 0 or chunk.shape[1] == 0:
            return
        try:
            hashes = pd.util.hash_pandas_object(chunk, index=False)
        except TypeError:
            # Unhashable cell (e.g. list/dict values) — skip dup detection.
            return
        for value in hashes.to_numpy():
            key = int(value)
            if key in self._seen_hashes:
                self.duplicate_rows += 1
            elif len(self._seen_hashes) < _DUP_HASH_CAP:
                self._seen_hashes.add(key)
            else:
                self.duplicate_rows_approx = True

    def _update_column(self, state: _ColumnState, series: pd.Series) -> None:
        if not state.dtype:
            state.dtype = str(series.dtype)
        if state.is_numeric is None:
            state.is_numeric = bool(pd.api.types.is_numeric_dtype(series))

        state.missing += int(series.isna().sum())
        non_null = series.dropna()

        if not state.distinct_capped:
            for value, freq in non_null.value_counts().items():
                if value in state.counts or len(state.counts) < _DISTINCT_CAP:
                    state.counts[value] += int(freq)
                else:
                    state.distinct_capped = True
                    break

        if state.is_numeric:
            numeric = pd.to_numeric(non_null, errors="coerce").dropna()
            if len(numeric):
                state.n_sum += float(numeric.sum())
                state.n_count += int(numeric.size)
                chunk_min = float(numeric.min())
                chunk_max = float(numeric.max())
                state.n_min = chunk_min if state.n_min is None else min(state.n_min, chunk_min)
                state.n_max = chunk_max if state.n_max is None else max(state.n_max, chunk_max)
                if len(state.reservoir) < _RESERVOIR_CAP:
                    room = _RESERVOIR_CAP - len(state.reservoir)
                    state.reservoir.extend(numeric.head(room).tolist())
        else:
            text = non_null[non_null.map(lambda v: isinstance(v, str))]
            if len(text):
                state.whitespace += int((text.str.strip() != text).sum())

    # ---- finalize ---------------------------------------------------------
    def finalize(self) -> DataQualityReport:
        profiles = [self._profile(name) for name in self.columns]
        issues = self._issues(profiles)
        score, grade = self._score(profiles, issues)
        return DataQualityReport(
            rows=self.rows,
            columns=len(self.columns),
            duplicate_rows=self.duplicate_rows,
            duplicate_rows_approx=self.duplicate_rows_approx,
            score=score,
            grade=grade,
            generated_at=datetime.now().isoformat(timespec="seconds"),
            column_profiles=profiles,
            issues=issues,
        )

    def _profile(self, name: str) -> ColumnProfile:
        state = self._state[name]
        count = self.rows - state.missing
        distinct = len(state.counts)
        top_value, top_count = ("", 0)
        if state.counts:
            top_value, top_count = state.counts.most_common(1)[0]
        sample = [str(v) for v, _ in state.counts.most_common(3)]
        mean = (state.n_sum / state.n_count) if state.n_count else None
        return ColumnProfile(
            name=name,
            dtype=state.dtype or "object",
            count=count,
            missing=state.missing,
            missing_pct=(100.0 * state.missing / self.rows) if self.rows else 0.0,
            distinct=distinct,
            distinct_pct=(100.0 * distinct / count) if count else 0.0,
            distinct_capped=state.distinct_capped,
            top_value=str(top_value),
            top_count=int(top_count),
            numeric_min=state.n_min,
            numeric_max=state.n_max,
            numeric_mean=mean,
            sample=sample,
        )

    def _issues(self, profiles: Sequence[ColumnProfile]) -> list[Issue]:
        issues: list[Issue] = []
        if self.duplicate_rows > 0:
            detail = f"{self.duplicate_rows:,} fully duplicated row(s)"
            if self.duplicate_rows_approx:
                detail += " (approx — dataset exceeded the hash cap)"
            issues.append(Issue("watch", "duplicate rows", "(row)", self.duplicate_rows, detail))

        for profile in profiles:
            issues.extend(self._column_issues(profile))
        # Alerts first, then by count desc, so the worst is on top.
        issues.sort(key=lambda i: (0 if i.severity == "alert" else 1, -i.count))
        return issues

    def _column_issues(self, profile: ColumnProfile) -> list[Issue]:
        issues: list[Issue] = []
        name = profile.name
        state = self._state[name]
        lowered = name.lower()

        if self.rows and profile.missing == self.rows:
            issues.append(
                Issue("alert", "empty column", name, profile.missing, "column is 100% null")
            )
        elif profile.missing_pct >= self.missing_alert_pct and profile.missing > 0:
            issues.append(
                Issue(
                    "watch",
                    "high missing",
                    name,
                    profile.missing,
                    f"{profile.missing_pct:.1f}% of values are missing",
                )
            )

        if self.rows > 1 and profile.count > 0 and profile.distinct == 1:
            issues.append(
                Issue("watch", "constant column", name, self.rows, "only one distinct value")
            )

        if any(hint in lowered for hint in KEY_HINTS) and profile.count > profile.distinct > 0:
            dup_keys = profile.count - profile.distinct
            issues.append(
                Issue(
                    "alert",
                    "duplicate keys",
                    name,
                    dup_keys,
                    f"key-like column has {dup_keys:,} duplicate value(s)",
                )
            )

        if state.is_numeric and any(hint in lowered for hint in AMOUNT_HINTS):
            negatives = sum(v for value, v in state.counts.items() if _as_float(value) < 0)
            if negatives:
                issues.append(
                    Issue("watch", "negative amount", name, negatives, "negative value(s) found")
                )

        if state.is_numeric and len(state.reservoir) >= 4:
            outliers = _iqr_outliers(state.reservoir)
            if outliers:
                issues.append(
                    Issue(
                        "watch",
                        "outliers",
                        name,
                        outliers,
                        f"{outliers:,} value(s) beyond 1.5×IQR",
                    )
                )

        if state.whitespace:
            issues.append(
                Issue(
                    "watch",
                    "whitespace",
                    name,
                    state.whitespace,
                    "leading/trailing spaces in text value(s)",
                )
            )
        return issues

    def _score(
        self, profiles: Sequence[ColumnProfile], issues: Sequence[Issue]
    ) -> tuple[float, str]:
        total_cells = self.rows * len(self.columns)
        total_missing = sum(p.missing for p in profiles)
        completeness = 1.0 - (total_missing / total_cells) if total_cells else 1.0
        uniqueness = 1.0 - (self.duplicate_rows / self.rows) if self.rows else 1.0
        penalty = sum(0.10 if i.severity == "alert" else 0.03 for i in issues)
        validity = max(0.0, 1.0 - min(1.0, penalty))
        raw = 100.0 * (0.5 * completeness + 0.25 * uniqueness + 0.25 * validity)
        score = round(max(0.0, min(100.0, raw)), 1)
        grade = _grade(score)
        return score, grade


# ---- public API -----------------------------------------------------------
def profile_frame(frame: pd.DataFrame, *, missing_alert_pct: float = 20.0) -> DataQualityReport:
    """Profile an in-memory DataFrame (SQL results, moderate files)."""
    accumulator = _Accumulator(missing_alert_pct=missing_alert_pct)
    accumulator.update(frame)
    return accumulator.finalize()


def profile_chunks(
    chunks: Iterable[pd.DataFrame], *, missing_alert_pct: float = 20.0
) -> DataQualityReport:
    """Profile an iterable of row-chunks (the streaming core)."""
    accumulator = _Accumulator(missing_alert_pct=missing_alert_pct)
    for chunk in chunks:
        accumulator.update(chunk)
    return accumulator.finalize()


def profile_csv(
    path: str | Path,
    *,
    chunk_size: int = 50_000,
    missing_alert_pct: float = 20.0,
    **read_csv_kwargs: object,
) -> DataQualityReport:
    """Profile a CSV/TSV by streaming it in ``chunk_size`` row batches."""
    reader = pd.read_csv(path, chunksize=chunk_size, **read_csv_kwargs)
    return profile_chunks(reader, missing_alert_pct=missing_alert_pct)


def profile_path(
    path: str | Path, *, chunk_size: int = 50_000, missing_alert_pct: float = 20.0
) -> DataQualityReport:
    """Profile any supported file, streaming CSV/TSV and loading Excel whole."""
    suffix = Path(path).suffix.lower()
    if suffix in (".csv", ".txt"):
        return profile_csv(path, chunk_size=chunk_size, missing_alert_pct=missing_alert_pct)
    if suffix == ".tsv":
        return profile_csv(
            path, chunk_size=chunk_size, missing_alert_pct=missing_alert_pct, sep="\t"
        )
    if suffix in (".xlsx", ".xls"):
        return profile_frame(pd.read_excel(path), missing_alert_pct=missing_alert_pct)
    raise ValueError(f"unsupported file type for profiling: {suffix or path}")


def export_report(report: DataQualityReport, path: str | Path) -> Path:
    """Write a management-ready exception workbook (summary/profiles/issues)."""
    out = Path(path)
    overview = pd.DataFrame(
        {
            "metric": [
                "Rows",
                "Columns",
                "Duplicate rows",
                "Quality score",
                "Grade",
                "Generated",
            ],
            "value": [
                report.rows,
                report.columns,
                report.duplicate_rows,
                f"{report.score:.0f}/100",
                report.grade,
                report.generated_at,
            ],
        }
    )
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        overview.to_excel(writer, sheet_name="Summary", index=False)
        report.profiles_frame().to_excel(writer, sheet_name="Column Profiles", index=False)
        report.issues_frame().to_excel(writer, sheet_name="Exceptions", index=False)
    return out


# ---- helpers --------------------------------------------------------------
def _as_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _iqr_outliers(values: Sequence[float]) -> int:
    series = pd.Series(values, dtype="float64")
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    if math.isnan(iqr) or iqr == 0:
        return 0
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return int(((series < low) | (series > high)).sum())


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"
