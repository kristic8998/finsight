"""Deterministic sample lending dataset for the MIS Studio demos.

One rich frame that works with the Visual Builder *and* all three
one-click templates, so a layman can try everything before touching a
real export. Seeded — identical on every machine.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_BRANCHES = ["Kolkata", "Mumbai", "Delhi", "Bengaluru", "Pune", "Jaipur", "Indore", "Kochi"]
_PRODUCTS = ["Personal Loan", "Education Loan", "Consumer Durable", "Two Wheeler"]
_SEGMENTS = ["student", "salaried", "self-employed"]
_FIRST = ["Aarav", "Isha", "Rohan", "Priya", "Kabir", "Ananya", "Dev", "Meera", "Sana", "Tara"]
_LAST = ["Sharma", "Patel", "Iyer", "Khan", "Das", "Nair", "Gupta", "Bose"]


def sample_lending_dataset(n: int = 500, seed: int = 17) -> pd.DataFrame:
    """Raw 'export from the LMS' style dataset covering all MIS use-cases."""
    rng = np.random.default_rng(seed)
    today = pd.Timestamp.today().normalize()
    dates = today - pd.to_timedelta(rng.integers(0, 30, n), unit="D")
    amount = (rng.uniform(8_000, 120_000, n)).round(-2)
    outstanding = (amount * rng.uniform(0.05, 1.0, n)).round(0)
    dpd = np.where(rng.random(n) < 0.7, 0, rng.integers(1, 120, n))
    emi_due = (amount * 0.09).round(0)
    emi_paid = np.where(dpd > 0, (emi_due * rng.uniform(0.0, 0.8, n)).round(0), emi_due)
    return pd.DataFrame(
        {
            "loan_id": [f"L{i:05d}" for i in range(1, n + 1)],
            "customer_name": [f"{rng.choice(_FIRST)} {rng.choice(_LAST)}" for _ in range(n)],
            "disbursed_date": dates.strftime("%Y-%m-%d"),
            "branch": rng.choice(_BRANCHES, n),
            "product": rng.choice(_PRODUCTS, n),
            "segment": rng.choice(_SEGMENTS, n, p=[0.35, 0.45, 0.2]),
            "loan_amount": amount,
            "outstanding": outstanding,
            "emi_due": emi_due,
            "emi_paid": emi_paid,
            "current_dpd": dpd,
        }
    )
