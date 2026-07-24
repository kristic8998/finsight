"""Synthetic lending book generator.

Builds a realistic NBFC-style demo database (branches, officers, loans,
payment schedules with real delinquency behaviour, collection targets)
so every module works out of the box. Deterministic per seed; dates are
generated relative to *today* so dashboards always look live.

Schema (also the canonical schema the NLQ and Executive modules query):
    branches(id, name, city, region, opened_on)
    officers(id, branch_id, name, role)
    loans(id, branch_id, officer_id, customer_name, product, principal,
          interest_rate, tenure_months, emi, disbursed_on, status)
    payments(id, loan_id, due_date, amount_due, paid_date, amount_paid, mode)
    collection_targets(branch_id, month, target_amount)
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from ..core.config import DemoConfig
from ..core.paths import demo_db_path

logger = logging.getLogger(__name__)

PRODUCTS = ("Personal Loan", "Business Loan", "Gold Loan", "Vehicle Loan")
PAY_MODES = ("UPI", "NACH", "Cash", "Bank Transfer")

_CITIES = [
    ("Mumbai Central", "Mumbai", "West"),
    ("Andheri", "Mumbai", "West"),
    ("Pune Camp", "Pune", "West"),
    ("Kolkata Park St", "Kolkata", "East"),
    ("Salt Lake", "Kolkata", "East"),
    ("Chennai T Nagar", "Chennai", "South"),
    ("Bengaluru MG Road", "Bengaluru", "South"),
    ("Hyderabad Banjara", "Hyderabad", "South"),
    ("Delhi Karol Bagh", "Delhi", "North"),
    ("Gurugram Cyber", "Gurugram", "North"),
    ("Jaipur Pink Sq", "Jaipur", "North"),
    ("Lucknow Hazrat", "Lucknow", "North"),
]

_FIRST = [
    "Aarav",
    "Diya",
    "Rohan",
    "Priya",
    "Kabir",
    "Ananya",
    "Vikram",
    "Sneha",
    "Arjun",
    "Meera",
    "Rahul",
    "Pooja",
    "Sanjay",
    "Nisha",
    "Amit",
    "Kavya",
]
_LAST = [
    "Sharma",
    "Patel",
    "Reddy",
    "Iyer",
    "Khan",
    "Das",
    "Gupta",
    "Nair",
    "Singh",
    "Chatterjee",
    "Joshi",
    "Kulkarni",
]

_SCHEMA = """
CREATE TABLE branches (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT NOT NULL,
    region TEXT NOT NULL, opened_on TEXT NOT NULL
);
CREATE TABLE officers (
    id INTEGER PRIMARY KEY, branch_id INTEGER NOT NULL REFERENCES branches(id),
    name TEXT NOT NULL, role TEXT NOT NULL
);
CREATE TABLE loans (
    id INTEGER PRIMARY KEY, branch_id INTEGER NOT NULL REFERENCES branches(id),
    officer_id INTEGER NOT NULL REFERENCES officers(id),
    customer_name TEXT NOT NULL, product TEXT NOT NULL,
    principal REAL NOT NULL, interest_rate REAL NOT NULL,
    tenure_months INTEGER NOT NULL, emi REAL NOT NULL,
    disbursed_on TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE payments (
    id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL REFERENCES loans(id),
    due_date TEXT NOT NULL, amount_due REAL NOT NULL,
    paid_date TEXT, amount_paid REAL NOT NULL DEFAULT 0, mode TEXT
);
CREATE TABLE collection_targets (
    branch_id INTEGER NOT NULL REFERENCES branches(id),
    month TEXT NOT NULL, target_amount REAL NOT NULL,
    PRIMARY KEY (branch_id, month)
);
CREATE INDEX idx_loans_branch ON loans(branch_id);
CREATE INDEX idx_payments_loan ON payments(loan_id);
CREATE INDEX idx_payments_due ON payments(due_date);
"""


@dataclass
class DemoSummary:
    path: Path
    branches: int
    officers: int
    loans: int
    payments: int


def _emi(principal: float, annual_rate: float, months: int) -> float:
    monthly = annual_rate / 12 / 100
    if monthly <= 0:
        return principal / months
    factor = (1 + monthly) ** months
    return principal * monthly * factor / (factor - 1)


def generate_demo_db(
    config: DemoConfig, path: Path | str | None = None, force: bool = False
) -> DemoSummary:
    """Create (or reuse) the demo lending database.

    Idempotent: if the file exists and ``force`` is False, it is kept —
    first launch stays fast and user modifications survive restarts.
    """
    db_path = Path(path) if path is not None else demo_db_path()
    if db_path.exists() and not force:
        with sqlite3.connect(db_path) as conn:
            counts = {
                t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608
                for t in ("branches", "officers", "loans", "payments")
            }
        return DemoSummary(
            db_path, counts["branches"], counts["officers"], counts["loans"], counts["payments"]
        )

    rng = np.random.default_rng(config.seed)
    today = date.today()
    db_path.unlink(missing_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)

        # Branches — each gets a hidden "quality" factor driving delinquency,
        # so rankings and risk analytics have real signal to find.
        n_branches = min(config.branches, len(_CITIES))
        quality: dict[int, float] = {}
        for branch_id in range(1, n_branches + 1):
            name, city, region = _CITIES[branch_id - 1]
            opened = today - timedelta(days=int(rng.integers(400, 3000)))
            conn.execute(
                "INSERT INTO branches VALUES (?,?,?,?,?)",
                (branch_id, name, city, region, opened.isoformat()),
            )
            quality[branch_id] = float(rng.uniform(0.55, 0.97))

        officer_id = 0
        officers_by_branch: dict[int, list[int]] = {}
        for branch_id in range(1, n_branches + 1):
            officers_by_branch[branch_id] = []
            for _ in range(int(rng.integers(3, 7))):
                officer_id += 1
                name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
                role = "Collection Officer" if rng.random() < 0.6 else "Loan Officer"
                conn.execute(
                    "INSERT INTO officers VALUES (?,?,?,?)",
                    (officer_id, branch_id, name, role),
                )
                officers_by_branch[branch_id].append(officer_id)

        payment_id = 0
        n_payments = 0
        for loan_id in range(1, config.loans + 1):
            branch_id = int(rng.integers(1, n_branches + 1))
            product = str(rng.choice(PRODUCTS, p=[0.4, 0.25, 0.2, 0.15]))
            principal = (
                float(
                    rng.choice([50, 100, 150, 200, 300, 500], p=[0.25, 0.25, 0.2, 0.15, 0.1, 0.05])
                )
                * 1000
            )
            rate = float(rng.uniform(11, 24))
            tenure = int(rng.choice([12, 18, 24, 36]))
            emi = round(_emi(principal, rate, tenure), 2)
            disbursed = today - timedelta(days=int(rng.integers(30, 720)))
            customer = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"

            # Borrower discipline blends branch quality with personal noise.
            discipline = float(np.clip(quality[branch_id] + rng.normal(0, 0.12), 0.05, 0.995))

            months_elapsed = max(
                0, (today.year - disbursed.year) * 12 + today.month - disbursed.month
            )
            schedule_len = min(tenure, months_elapsed + 3)  # a few future EMIs too
            missed_recent = 0
            total_paid_installments = 0

            rows = []
            for k in range(1, schedule_len + 1):
                due = _add_months(disbursed, k)
                payment_id += 1
                if due > today:  # future installment
                    rows.append((payment_id, loan_id, due.isoformat(), emi, None, 0.0, None))
                    continue
                if rng.random() < discipline:
                    lag = int(rng.integers(0, 6))
                    paid_on = min(due + timedelta(days=lag), today)
                    partial = rng.random() < 0.06
                    paid_amount = round(emi * (rng.uniform(0.3, 0.9) if partial else 1.0), 2)
                    mode = str(rng.choice(PAY_MODES, p=[0.45, 0.3, 0.15, 0.10]))
                    rows.append(
                        (
                            payment_id,
                            loan_id,
                            due.isoformat(),
                            emi,
                            paid_on.isoformat(),
                            paid_amount,
                            mode,
                        )
                    )
                    total_paid_installments += 1
                    if not partial:
                        missed_recent = 0
                else:
                    rows.append((payment_id, loan_id, due.isoformat(), emi, None, 0.0, None))
                    missed_recent += 1
            conn.executemany("INSERT INTO payments VALUES (?,?,?,?,?,?,?)", rows)
            n_payments += len(rows)

            if total_paid_installments >= tenure:
                status = "closed"
            elif missed_recent >= 3:
                status = "npa"
            else:
                status = "active"
            conn.execute(
                "INSERT INTO loans VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    loan_id,
                    branch_id,
                    int(rng.choice(officers_by_branch[branch_id])),
                    customer,
                    product,
                    principal,
                    round(rate, 2),
                    tenure,
                    emi,
                    disbursed.isoformat(),
                    status,
                ),
            )

        # Monthly collection targets: expected dues x ambition factor.
        for branch_id in range(1, n_branches + 1):
            for offset in range(0, 7):
                month_start = _add_months(today.replace(day=1), -offset)
                month_key = month_start.strftime("%Y-%m")
                due_total = conn.execute(
                    "SELECT COALESCE(SUM(p.amount_due),0) FROM payments p"
                    " JOIN loans l ON l.id = p.loan_id"
                    " WHERE l.branch_id=? AND substr(p.due_date,1,7)=?",
                    (branch_id, month_key),
                ).fetchone()[0]
                target = round(float(due_total) * float(rng.uniform(0.95, 1.1)), 2)
                conn.execute(
                    "INSERT OR REPLACE INTO collection_targets VALUES (?,?,?)",
                    (branch_id, month_key, target),
                )
        conn.commit()

    summary = DemoSummary(db_path, n_branches, officer_id, config.loans, n_payments)
    logger.info(
        "demo db generated: %d branches, %d officers, %d loans, %d payments at %s",
        summary.branches,
        summary.officers,
        summary.loans,
        summary.payments,
        db_path,
    )
    return summary


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last_day = [
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ][month - 1]
    return date(year, month, min(day.day, last_day))
