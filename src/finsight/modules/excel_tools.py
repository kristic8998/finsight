"""Excel Intelligence: merge, split, compare, profile, clean, Excel↔SQL.

Every function takes/returns DataFrames or file paths, so the same code
serves the UI, the automation scheduler, and tests. Reading supports
.xlsx/.xls/.csv transparently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class ExcelToolsError(Exception):
    """Raised for unusable spreadsheet inputs."""


def read_table(path: Path | str, sheet: str | int = 0) -> pd.DataFrame:
    """Read xlsx/xls/csv into a DataFrame with helpful errors."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ExcelToolsError(f"file not found: {file_path}")
    try:
        if file_path.suffix.lower() == ".csv":
            return pd.read_csv(file_path)
        return pd.read_excel(file_path, sheet_name=sheet)
    except Exception as exc:
        raise ExcelToolsError(f"cannot read {file_path.name}: {exc}") from exc


def merge_files(paths: list[Path | str], add_source_column: bool = True) -> pd.DataFrame:
    """Stack many files with the same layout into one frame."""
    if not paths:
        raise ExcelToolsError("no files given to merge")
    frames = []
    for p in paths:
        frame = read_table(p)
        if add_source_column:
            frame = frame.copy()
            frame["source_file"] = Path(p).name
        frames.append(frame)
    columns = list(frames[0].columns)
    for i, frame in enumerate(frames[1:], start=2):
        if list(frame.columns) != columns:
            raise ExcelToolsError(
                f"file #{i} has different columns than the first file — "
                "align headers before merging"
            )
    return pd.concat(frames, ignore_index=True)


def split_file(path: Path | str, by_column: str, out_dir: Path | str) -> list[Path]:
    """Split one file into one xlsx per distinct value of ``by_column``."""
    frame = read_table(path)
    if by_column not in frame.columns:
        raise ExcelToolsError(f"column '{by_column}' not found")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for value, part in frame.groupby(by_column):
        safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in str(value))[:40]
        target = out / f"{Path(path).stem}_{safe}.xlsx"
        part.to_excel(target, index=False)
        written.append(target)
    return written


@dataclass
class CompareResult:
    only_left: pd.DataFrame
    only_right: pd.DataFrame
    changed: pd.DataFrame  # key + column + left/right values

    @property
    def identical(self) -> bool:
        return self.only_left.empty and self.only_right.empty and self.changed.empty


def compare_files(left: pd.DataFrame, right: pd.DataFrame, key: str) -> CompareResult:
    """Row-level diff of two frames sharing a key column."""
    for name, frame in (("left", left), ("right", right)):
        if key not in frame.columns:
            raise ExcelToolsError(f"key '{key}' missing in {name} file")
    left_i = left.astype({key: str}).set_index(key)
    right_i = right.astype({key: str}).set_index(key)

    only_left = left_i.loc[~left_i.index.isin(right_i.index)].reset_index()
    only_right = right_i.loc[~right_i.index.isin(left_i.index)].reset_index()

    shared = left_i.index.intersection(right_i.index)
    common_cols = [c for c in left_i.columns if c in right_i.columns]
    changes = []
    left_s, right_s = left_i.loc[shared, common_cols], right_i.loc[shared, common_cols]
    for column in common_cols:
        l_col = left_s[column].astype(str).str.strip()
        r_col = right_s[column].astype(str).str.strip()
        diff_mask = l_col != r_col
        for idx in left_s.index[diff_mask]:
            changes.append(
                {
                    key: idx,
                    "column": column,
                    "left": left_s.at[idx, column],
                    "right": right_s.at[idx, column],
                }
            )
    changed = pd.DataFrame(changes, columns=[key, "column", "left", "right"])
    return CompareResult(only_left=only_left, only_right=only_right, changed=changed)


def profile(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-column data-quality profile: missing, unique, duplicates, dtype."""
    rows = []
    for column in frame.columns:
        series = frame[column]
        rows.append(
            {
                "column": column,
                "dtype": str(series.dtype),
                "rows": int(len(series)),
                "missing": int(series.isna().sum()),
                "missing_pct": round(float(series.isna().mean() * 100), 1),
                "unique": int(series.nunique(dropna=True)),
                "sample": str(series.dropna().iloc[0]) if series.notna().any() else "",
            }
        )
    return pd.DataFrame(rows)


@dataclass
class CleanReport:
    frame: pd.DataFrame
    actions: list[str]


def clean(
    frame: pd.DataFrame,
    trim_text: bool = True,
    drop_duplicate_rows: bool = True,
    drop_empty_rows: bool = True,
    standardise_headers: bool = True,
    parse_dates: bool = True,
) -> CleanReport:
    """One-click cleaning with an audit trail of what changed."""
    out = frame.copy()
    actions: list[str] = []

    if standardise_headers:
        new_cols = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
        if new_cols != list(out.columns):
            out.columns = new_cols
            actions.append("standardised headers to snake_case")
    if drop_empty_rows:
        before = len(out)
        out = out.dropna(how="all")
        if len(out) != before:
            actions.append(f"dropped {before - len(out)} fully-empty row(s)")
    if trim_text:
        touched = 0
        for column in out.select_dtypes(include="object").columns:
            cleaned = out[column].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
            touched += int((cleaned != out[column].astype("string")).sum())
            out[column] = cleaned
        if touched:
            actions.append(f"trimmed/collapsed whitespace in {touched} cell(s)")
    if drop_duplicate_rows:
        before = len(out)
        out = out.drop_duplicates()
        if len(out) != before:
            actions.append(f"removed {before - len(out)} duplicate row(s)")
    if parse_dates:
        for column in out.select_dtypes(include=["object", "string"]).columns:
            sample = out[column].dropna().head(50)
            if sample.empty:
                continue
            parsed = pd.to_datetime(sample, errors="coerce", format="mixed", dayfirst=False)
            if parsed.notna().mean() >= 0.9:
                out[column] = pd.to_datetime(
                    out[column], errors="coerce", format="mixed", dayfirst=False
                )
                actions.append(f"parsed '{column}' as dates")
    if not actions:
        actions.append("no changes needed — data already clean")
    return CleanReport(frame=out.reset_index(drop=True), actions=actions)


def excel_to_sql(
    path: Path | str,
    engine: Engine,
    table: str,
    if_exists: str = "replace",
    chunksize: int = 5000,
) -> int:
    """Load a spreadsheet into a database table (chunked for big files)."""
    frame = read_table(path)
    frame.to_sql(table, engine, if_exists=if_exists, index=False, chunksize=chunksize)
    logger.info("loaded %d rows from %s into table %s", len(frame), Path(path).name, table)
    return int(len(frame))


def sql_to_excel(frame: pd.DataFrame, path: Path | str, sheet: str = "Data") -> Path:
    """Write a result frame to a formatted xlsx (frozen header, autofit)."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet[:31], index=False)
        ws = writer.sheets[sheet[:31]]
        ws.freeze_panes = "A2"
        for column_cells in ws.columns:
            width = max((len(str(c.value)) for c in column_cells if c.value is not None), default=8)
            ws.column_dimensions[column_cells[0].column_letter].width = min(width + 2, 40)
    return out_path
