"""Deterministic synthetic transactions generator.

Produces a transactions table with the canonical schema
``customer_id`` / ``order_date`` / ``revenue`` that the rest of the
toolkit consumes. Given the same ``seed`` it always produces byte-for-byte
identical output, so tests and README examples are reproducible offline.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd


def _add_months(anchor: date, months: int) -> date:
    """Return ``anchor`` shifted by ``months`` calendar months (day clamped)."""
    month_index = anchor.month - 1 + months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def generate_transactions(
    n_customers: int = 800,
    n_months: int = 12,
    start: date = date(2023, 1, 1),
    seed: int = 42,
    base_retention: float = 0.80,
) -> pd.DataFrame:
    """Generate a deterministic synthetic transactions table.

    Each customer is acquired in one of the first ``n_months`` cohort months.
    In every subsequent month they remain active with a decaying probability
    (``base_retention`` compounded), and an active customer places one to three
    orders. Revenue is drawn from a bounded log-ish distribution.

    Args:
        n_customers: Number of distinct customers to create.
        n_months: Number of monthly cohorts / observation window in months.
        start: First calendar month (day is ignored; truncated to month start).
        seed: PRNG seed. Identical seeds yield identical tables.
        base_retention: Per-month survival probability at ``month_index == 1``.

    Returns:
        A tidy ``pd.DataFrame`` with columns ``customer_id`` (str),
        ``order_date`` (``datetime64[ns]``) and ``revenue`` (float), sorted by
        ``order_date`` then ``customer_id``.
    """
    if n_customers <= 0:
        raise ValueError("n_customers must be positive")
    if n_months <= 0:
        raise ValueError("n_months must be positive")
    if not 0.0 < base_retention <= 1.0:
        raise ValueError("base_retention must be in (0, 1]")

    rng = random.Random(seed)
    start_month = date(start.year, start.month, 1)

    rows: list[tuple[str, date, float]] = []
    for i in range(n_customers):
        customer_id = f"C{i:05d}"
        # Weight acquisition toward earlier cohorts so later cohorts are smaller.
        cohort_offset = min(int(rng.triangular(0, n_months - 1, 0)), n_months - 1)
        # A per-customer "quality" multiplier makes retention heterogeneous.
        loyalty = rng.uniform(0.75, 1.15)
        spend_level = rng.uniform(20.0, 120.0)

        for month_index in range(n_months - cohort_offset):
            if month_index == 0:
                active = True
            else:
                survival = min(base_retention * loyalty, 0.98) ** month_index
                active = rng.random() < survival
            if not active:
                continue

            order_month = _add_months(start_month, cohort_offset + month_index)
            n_orders = rng.randint(1, 3)
            for _ in range(n_orders):
                day = rng.randint(0, 27)
                order_date = order_month + timedelta(days=day)
                revenue = round(spend_level * rng.uniform(0.5, 1.8), 2)
                rows.append((customer_id, order_date, revenue))

    frame = pd.DataFrame(rows, columns=["customer_id", "order_date", "revenue"])
    frame["order_date"] = pd.to_datetime(frame["order_date"])
    frame = frame.sort_values(["order_date", "customer_id"]).reset_index(drop=True)
    return frame
