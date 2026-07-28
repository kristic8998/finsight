"""Visual MIS Builder — a zero-code dynamic pivot engine.

Pure pandas, no UI. The wizard page collects a :class:`BuilderConfig`
(group by → optional split by → metric → aggregate) from dropdowns that
are populated from the uploaded file's own headers; :func:`build_pivot`
turns it into a tidy pivot with a TOTAL row, and :func:`export_pivot`
writes a formatted, boardroom-ready Excel sheet.

Configurations can be saved by name (:func:`save_report`) — that is what
the Visual Auto-Reporter schedules later.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from ..core.paths import app_data_dir
from .amounts import parse_amount_series
from .excel_style import write_formatted_sheet

logger = logging.getLogger(__name__)

AGGREGATES: dict[str, str] = {
    "Sum": "sum",
    "Average": "mean",
    "Median": "median",
    "Count": "count",
    "Count Distinct": "nunique",
    "Minimum": "min",
    "Maximum": "max",
}

# Aggregates that work on the raw values (no numeric coercion needed).
_RAW_VALUE_AGGS = ("count", "nunique")

NO_SPLIT = "(none)"


@dataclass(frozen=True)
class BuilderConfig:
    """What the user picked in the wizard."""

    group_by: str
    value: str
    aggregate: str = "Sum"  # a key of AGGREGATES
    split_by: str | None = None  # optional second dimension (pivot columns)

    def title(self) -> str:
        text = f"{self.aggregate} of {self.value} by {self.group_by}"
        if self.split_by:
            text += f", split by {self.split_by}"
        return text


@dataclass
class PivotResult:
    frame: pd.DataFrame  # first column = group values (+ TOTAL row)
    title: str
    config: BuilderConfig
    rows_used: int


def _validate(frame: pd.DataFrame, config: BuilderConfig) -> None:
    if frame is None or frame.empty:
        raise ValueError("the uploaded file has no rows")
    if config.aggregate not in AGGREGATES:
        raise ValueError(f"unknown aggregate: {config.aggregate}")
    for label, column in (
        ("Group by", config.group_by),
        ("Metric", config.value),
        ("Split by", config.split_by),
    ):
        if column and column not in frame.columns:
            raise ValueError(
                f"the '{label}' column ({column}) is not in this file — "
                f"re-upload the file or pick another column"
            )
    if config.split_by and config.split_by == config.group_by:
        raise ValueError("'Group by' and 'Split by' must be different columns")


def build_pivot(frame: pd.DataFrame, config: BuilderConfig) -> PivotResult:
    """Run the pivot exactly as the wizard describes it."""
    _validate(frame, config)
    df = frame.dropna(how="all").copy()  # real exports carry fully blank rows
    aggfunc = AGGREGATES[config.aggregate]
    if aggfunc not in _RAW_VALUE_AGGS:
        # Robust coercion: "Rs 1,20,000.00", "(2,500)", "24%" all become numbers.
        df[config.value] = parse_amount_series(df[config.value])
    df[config.group_by] = df[config.group_by].fillna("(blank)").astype(str)

    if config.split_by:
        df[config.split_by] = df[config.split_by].fillna("(blank)").astype(str)
        pivot = pd.pivot_table(
            df,
            index=config.group_by,
            columns=config.split_by,
            values=config.value,
            aggfunc=aggfunc,
            fill_value=0,
        )
        pivot.columns = [str(c) for c in pivot.columns]
        out = pivot.reset_index()
        value_cols = [c for c in out.columns if c != config.group_by]
    else:
        series = df.groupby(config.group_by)[config.value].agg(aggfunc)
        value_name = f"{config.aggregate} of {config.value}"
        out = series.reset_index().rename(columns={config.value: value_name})
        value_cols = [value_name]

    out = out.sort_values(value_cols[0], ascending=False).reset_index(drop=True)

    # TOTAL row: additive aggregates get a grand total; the rest recompute over
    # the WHOLE dataset (summing per-group medians/distincts would be wrong).
    totals: dict[str, object] = {config.group_by: "TOTAL"}
    for column in value_cols:
        if aggfunc in ("sum", "count"):
            totals[column] = out[column].sum()
        elif aggfunc == "mean":
            totals[column] = df[config.value].mean()
        elif aggfunc == "median":
            totals[column] = df[config.value].median()
        elif aggfunc == "nunique":
            totals[column] = df[config.value].nunique()
        elif aggfunc == "min":
            totals[column] = out[column].min()
        else:
            totals[column] = out[column].max()
    out = pd.concat([out, pd.DataFrame([totals])], ignore_index=True)
    for column in value_cols:
        out[column] = pd.to_numeric(out[column], errors="coerce").round(2)

    return PivotResult(frame=out, title=config.title(), config=config, rows_used=len(frame))


def export_pivot(result: PivotResult, path: str | Path) -> Path:
    """Write the pivot as a formatted single-sheet workbook (or CSV)."""
    out = Path(path)
    if out.suffix.lower() == ".csv":
        result.frame.to_csv(out, index=False)
        return out
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        write_formatted_sheet(writer, result.frame, "MIS Report", title=result.title)
    return out


# ---- saved reports (consumed by the Auto-Reporter) ---------------------------
@dataclass
class SavedReport:
    name: str
    source_path: str  # the raw data file this report is built from
    config: BuilderConfig


def _store_path(path: Path | None = None) -> Path:
    return path if path is not None else app_data_dir() / "mis_builder_reports.json"


def list_reports(path: Path | None = None) -> list[SavedReport]:
    file_path = _store_path(path)
    if not file_path.is_file():
        return []
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        return [
            SavedReport(
                name=item["name"],
                source_path=item.get("source_path", ""),
                config=BuilderConfig(**item["config"]),
            )
            for item in raw
        ]
    except Exception as exc:  # noqa: BLE001 - a bad store must never break the UI
        logger.warning("ignoring unreadable builder store %s: %s", file_path, exc)
        return []


def save_report(report: SavedReport, path: Path | None = None) -> None:
    if not report.name.strip():
        raise ValueError("give the report a name first")
    reports = [r for r in list_reports(path) if r.name != report.name]
    reports.append(report)
    payload = [
        {"name": r.name, "source_path": r.source_path, "config": asdict(r.config)} for r in reports
    ]
    file_path = _store_path(path)
    file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_report(name: str, path: Path | None = None) -> SavedReport | None:
    for report in list_reports(path):
        if report.name == name:
            return report
    return None


def delete_report(name: str, path: Path | None = None) -> None:
    reports = [r for r in list_reports(path) if r.name != name]
    payload = [
        {"name": r.name, "source_path": r.source_path, "config": asdict(r.config)} for r in reports
    ]
    _store_path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
