"""Standalone mock-data simulator for FinSight MIS Studio.

Generates realistic, edge-case-filled lending datasets so anyone can test
the Visual MIS Builder, the One-Click Lending Templates and the
Auto-Reporter without touching real customer data.

Run it from the repository root (no FinSight install required):

    python mock_data_simulator.py

Outputs (written to ./mock_data/):
    lending_book.xlsx        -- main dataset; feed this to all three templates
    lending_book.csv         -- identical rows, CSV flavour
    lending_book_stress.csv  -- deliberately hostile: messy headers, blanks,
                                duplicates, text-formatted numbers, extreme DPD

Only pandas / numpy / openpyxl are required. Everything is seeded, so two
runs produce identical files (change SEED for a fresh universe).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260726
OUT_DIR = Path(__file__).resolve().parent / "mock_data"

BRANCHES = ["Kolkata Central", "Howrah", "Salt Lake", "Siliguri", "Durgapur"]
PRODUCTS = ["Student Flexi", "Salary Advance", "Micro Business", "Emergency Loan"]
OFFICERS = ["A. Sen", "R. Das", "P. Mukherjee", "S. Khatun", "J. Roy"]
NAMES = [
    "Riya Ghosh",
    "Arjun Paul",
    "Sneha Banerjee",
    "Imran Ali",
    "Tanmay Dutta",
    "Priya Sharma",
    "Sourav Mondal",
    "Ayesha Khatun",
    "Debojit Nag",
    "Mou Sinha",
]


def build_lending_book(n: int = 400) -> pd.DataFrame:
    """A believable loan book with the edge cases the engines must survive."""
    rng = np.random.default_rng(SEED)
    dates = pd.Timestamp("2026-06-01") + pd.to_timedelta(
        rng.integers(0, 55, n), unit="D"
    )
    amount = rng.choice([5000, 10000, 15000, 25000, 40000, 60000], n).astype(float)
    outstanding = (amount * rng.uniform(0.05, 1.0, n)).round(0)
    # DPD spread that intentionally hits every bucket edge used by pd.cut:
    dpd = rng.choice(
        [0, 0, 0, 1, 15, 29, 30, 31, 45, 59, 60, 61, 89, 90, 91, 180, 365],
        n,
    ).astype(float)
    emi_due = (amount / 12).round(0)
    emi_paid = (emi_due * rng.uniform(0.0, 1.1, n)).round(0)  # >100% = advance payer

    df = pd.DataFrame(
        {
            "loan_id": [f"FSL{100000 + i}" for i in range(n)],
            "customer_name": rng.choice(NAMES, n),
            "branch": rng.choice(BRANCHES, n),
            "product": rng.choice(PRODUCTS, n),
            "officer": rng.choice(OFFICERS, n),
            "disbursed_date": dates,
            "loan_amount": amount,
            "outstanding": outstanding,
            "dpd": dpd,
            "emi_due": emi_due,
            "emi_paid": emi_paid,
        }
    )

    # --- deliberate edge cases (positions are stable thanks to the seed) ---
    df.loc[0, "outstanding"] = np.nan  # missing numeric
    df.loc[1, "dpd"] = np.nan  # missing DPD -> engine default
    df.loc[2, "loan_amount"] = 0.0  # zero-amount loan
    df.loc[3, "outstanding"] = -1500.0  # negative (refund/adjustment)
    df.loc[4, "customer_name"] = ""  # blank text field
    df.loc[5, "loan_amount"] = 5_000_000.0  # absurd outlier
    df.loc[6, "dpd"] = 999.0  # deep NPA
    df.loc[7, "customer_name"] = "রিয়া ঘোষ"  # unicode (Bengali) must survive
    return df


def build_stress_csv(base: pd.DataFrame) -> pd.DataFrame:
    """Hostile variant: messy headers, duplicate + blank rows, text numbers."""
    df = base.head(60).copy()
    df = pd.concat([df, df.head(3)], ignore_index=True)  # duplicate rows
    # One numeric column arrives as formatted TEXT, as real LMS exports do:
    df["emi_paid"] = df["emi_paid"].map(lambda v: "" if pd.isna(v) else f"{v:,.2f}")
    # Headers with stray spaces / different casing (find_col must still match):
    return df.rename(
        columns={
            "loan_amount": " Loan Amount ",
            "dpd": "DPD",
            "outstanding": "Outstanding ",
            "customer_name": "Customer Name",
        }
    )


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    book = build_lending_book()
    stress = build_stress_csv(book)

    xlsx = OUT_DIR / "lending_book.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        book.to_excel(writer, sheet_name="Loan Book", index=False)
    book.to_csv(OUT_DIR / "lending_book.csv", index=False)
    stress_path = OUT_DIR / "lending_book_stress.csv"
    stress.to_csv(stress_path, index=False)
    # splice a fully blank line into the middle -- a classic real-export defect
    lines = stress_path.read_text(encoding="utf-8").splitlines()
    lines.insert(31, "," * (len(stress.columns) - 1))
    stress_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Mock data written to:", OUT_DIR)
    print(f"  lending_book.xlsx        {len(book)} rows (all DPD bucket edges covered)")
    print(f"  lending_book.csv         {len(book)} rows")
    print(
        f"  lending_book_stress.csv  {len(stress)} rows (messy headers, blanks, text numbers)"
    )
    print("Next: open FinSight -> MIS Studio and upload any of these files.")


if __name__ == "__main__":
    main()
