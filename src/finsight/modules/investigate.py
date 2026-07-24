"""Root Cause Analyzer — explain *why* two datasets differ.

Takes a completed reconciliation and decomposes the net difference into
attributable causes with amounts, shares, affected records, and
recommended fixes — the answer an analyst types into the "why doesn't
this match" email every day, generated in one call:

    Net difference 5,43,200 explained by:
      1. missing in Statement       243 records   4,90,100  (90.2%)
      2. duplicate keys              18 records     31,600   (5.8%)
      3. amount mismatches           12 records     21,500   (4.0%)
      possible typo pairs: UTR1023 ≈ UTR-1023, ...

Also provides a composite Data Quality Score for any DataFrame
(completeness / uniqueness / consistency) used by the Excel profiler.
Fuzzy matching uses stdlib ``difflib`` — fast, deterministic, no extra
dependency on a 16 GB office laptop.
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field

import pandas as pd

from .recon import ReconResult

logger = logging.getLogger(__name__)


@dataclass
class Cause:
    """One attributed contributor to the difference."""

    category: str
    records: int
    amount_impact: float
    share_pct: float
    detail: str
    recommendation: str


@dataclass
class Investigation:
    """Full root-cause explanation of a reconciliation difference."""

    net_difference: float
    explained: float
    unexplained: float
    causes: list[Cause] = field(default_factory=list)
    typo_pairs: pd.DataFrame = field(default_factory=pd.DataFrame)
    narrative: str = ""

    def to_frame(self) -> pd.DataFrame:
        rows = [
            {
                "category": c.category,
                "records": c.records,
                "amount_impact": c.amount_impact,
                "share_pct": c.share_pct,
                "detail": c.detail,
                "recommendation": c.recommendation,
            }
            for c in self.causes
        ]
        return pd.DataFrame(
            rows,
            columns=[
                "category",
                "records",
                "amount_impact",
                "share_pct",
                "detail",
                "recommendation",
            ],
        )


def _find_typo_pairs(
    left_keys: list[str], right_keys: list[str], threshold: float = 0.85, limit: int = 50
) -> pd.DataFrame:
    """Keys unmatched on both sides that look like misspellings of each other.

    Classic root cause: 'UTR1023' in the ledger vs 'UTR-1023' from the
    bank — both show as missing, but they are the same transaction.
    """
    pairs: list[dict[str, object]] = []
    right_pool = [str(k) for k in right_keys]
    for raw in left_keys[:500]:  # cap work; recon keys beyond this are rare
        key = str(raw)
        matches = difflib.get_close_matches(key, right_pool, n=1, cutoff=threshold)
        if matches and matches[0] != key:
            ratio = difflib.SequenceMatcher(None, key, matches[0]).ratio()
            pairs.append(
                {
                    "left_key": key,
                    "right_key": matches[0],
                    "similarity": round(ratio, 3),
                }
            )
            if len(pairs) >= limit:
                break
    frame = pd.DataFrame(pairs, columns=["left_key", "right_key", "similarity"])
    return frame.sort_values("similarity", ascending=False).reset_index(drop=True)


def investigate(result: ReconResult) -> Investigation:
    """Decompose a reconciliation difference into explained causes."""
    amount = None
    for column in result.only_left.columns:
        if column != result.key:
            amount = column
            break
    net = float(result.stats["net_difference"])

    causes: list[Cause] = []

    missing_right_amt = float(result.only_left[amount].sum()) if amount else 0.0
    if len(result.only_left):
        causes.append(
            Cause(
                category=f"missing in {result.right_name}",
                records=int(len(result.only_left)),
                amount_impact=round(missing_right_amt, 2),
                share_pct=0.0,
                detail=f"present in {result.left_name} only",
                recommendation=f"pull these keys from the {result.right_name} source system "
                "for the same period; check cut-off timing",
            )
        )
    missing_left_amt = float(result.only_right[amount].sum()) if amount else 0.0
    if len(result.only_right):
        causes.append(
            Cause(
                category=f"missing in {result.left_name}",
                records=int(len(result.only_right)),
                amount_impact=round(-missing_left_amt, 2),
                share_pct=0.0,
                detail=f"present in {result.right_name} only",
                recommendation=f"book these into {result.left_name} or confirm they belong "
                "to another period/account",
            )
        )
    if len(result.amount_mismatch):
        mismatch_amt = float(result.amount_mismatch["difference"].sum())
        causes.append(
            Cause(
                category="amount mismatches",
                records=int(len(result.amount_mismatch)),
                amount_impact=round(mismatch_amt, 2),
                share_pct=0.0,
                detail=f"same key, different value (tolerance ±{result.tolerance})",
                recommendation="check charges/fees deducted at source, partial payments, "
                "and currency rounding rules",
            )
        )
    dup_left_n, dup_right_n = len(result.dup_left), len(result.dup_right)
    if dup_left_n or dup_right_n:
        dup_amt = 0.0
        if amount and dup_left_n:
            groups = result.dup_left.groupby(result.key)[amount]
            dup_amt += float((groups.sum() - groups.first()).sum())
        if amount and dup_right_n:
            groups = result.dup_right.groupby(result.key)[amount]
            dup_amt -= float((groups.sum() - groups.first()).sum())
        causes.append(
            Cause(
                category="duplicate keys",
                records=int(dup_left_n + dup_right_n),
                amount_impact=round(dup_amt, 2),
                share_pct=0.0,
                detail=f"{dup_left_n} in {result.left_name}, {dup_right_n} in {result.right_name} "
                "(amounts were aggregated for matching)",
                recommendation="deduplicate at source; check for double-posting or retried "
                "payment callbacks",
            )
        )

    explained = round(sum(c.amount_impact for c in causes), 2)
    gross = sum(abs(c.amount_impact) for c in causes) or 1e-9
    for cause in causes:
        cause.share_pct = round(abs(cause.amount_impact) / gross * 100, 1)
    causes.sort(key=lambda c: abs(c.amount_impact), reverse=True)

    typo_pairs = (
        _find_typo_pairs(
            result.only_left[result.key].astype(str).tolist(),
            result.only_right[result.key].astype(str).tolist(),
        )
        if (len(result.only_left) and len(result.only_right))
        else pd.DataFrame(columns=["left_key", "right_key", "similarity"])
    )

    lines = [f"Net difference {net:,.2f} — {len(causes)} contributing cause(s):"]
    for rank, cause in enumerate(causes, start=1):
        lines.append(
            f"{rank}. {cause.category}: {cause.records} record(s), "
            f"impact {cause.amount_impact:,.2f} ({cause.share_pct:.1f}%) → "
            f"{cause.recommendation}"
        )
    if len(typo_pairs):
        example = typo_pairs.iloc[0]
        lines.append(
            f"⚠ {len(typo_pairs)} unmatched key pair(s) look like typos "
            f"(e.g. '{example['left_key']}' ≈ '{example['right_key']}') — "
            "fixing key formats may match these automatically."
        )
    unexplained = round(net - explained, 2)
    if abs(unexplained) > max(0.01, abs(net) * 0.001):
        lines.append(
            f"Unexplained residual: {unexplained:,.2f} — "
            "review tolerance setting and opening balances."
        )
    else:
        lines.append("The difference is fully explained by the causes above.")

    investigation = Investigation(
        net_difference=net,
        explained=explained,
        unexplained=unexplained,
        causes=causes,
        typo_pairs=typo_pairs,
        narrative="\n".join(lines),
    )
    logger.info("investigation: %d cause(s), explained %.2f of %.2f", len(causes), explained, net)
    return investigation


@dataclass
class QualityScore:
    """Composite 0–100 data-quality score with named components."""

    overall: float
    completeness: float
    uniqueness: float
    consistency: float
    grade: str
    notes: list[str] = field(default_factory=list)


def quality_score(frame: pd.DataFrame) -> QualityScore:
    """Score a dataset: completeness, row uniqueness, and type consistency."""
    if frame.empty:
        return QualityScore(0.0, 0.0, 0.0, 0.0, "F", ["dataset is empty"])

    completeness = float((1 - frame.isna().mean().mean()) * 100)
    uniqueness = float((1 - frame.duplicated().mean()) * 100)

    # Consistency: object columns whose values parse uniformly as one type.
    object_columns = frame.select_dtypes(include=["object", "string"]).columns
    consistent = 0
    notes: list[str] = []
    for column in object_columns:
        sample = frame[column].dropna().astype(str).head(200)
        if sample.empty:
            consistent += 1
            continue
        numeric_share = pd.to_numeric(sample, errors="coerce").notna().mean()
        if 0.05 < numeric_share < 0.95:
            notes.append(f"column '{column}' mixes numbers and text")
        else:
            consistent += 1
    consistency = float(consistent / len(object_columns) * 100) if len(object_columns) else 100.0

    overall = round(0.45 * completeness + 0.35 * uniqueness + 0.20 * consistency, 1)
    grade = (
        "A"
        if overall >= 90
        else "B" if overall >= 75 else "C" if overall >= 60 else "D" if overall >= 40 else "F"
    )
    if completeness < 95:
        notes.append(f"missing cells: {100 - completeness:.1f}% of the dataset")
    if uniqueness < 100:
        notes.append(f"duplicate rows: {100 - uniqueness:.1f}%")
    return QualityScore(
        overall=overall,
        completeness=round(completeness, 1),
        uniqueness=round(uniqueness, 1),
        consistency=round(consistency, 1),
        grade=grade,
        notes=notes,
    )
