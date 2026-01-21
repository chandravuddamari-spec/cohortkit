"""Tests for cohort retention, revenue-by-cohort, RFM and segments.

Several tests build a tiny hand-authored transactions table so the expected
numbers can be verified by hand, independent of the synthetic generator.
"""

from __future__ import annotations

import pandas as pd
import pytest

from cohortkit import (
    cohort_retention,
    generate_transactions,
    retention_matrix,
    revenue_by_cohort,
    rfm_scores,
    segment_summary,
)


def tiny_tx() -> pd.DataFrame:
    """Two Jan cohorts, one Feb cohort, hand-verifiable retention/revenue.

    A: buys Jan (10), Feb (20)          -> cohort Jan, months 0,1
    B: buys Jan (30)                    -> cohort Jan, month 0 only
    C: buys Feb (40), Mar (5)           -> cohort Feb, months 0,1
    """
    rows = [
        ("A", "2023-01-15", 10.0),
        ("A", "2023-02-10", 20.0),
        ("B", "2023-01-20", 30.0),
        ("C", "2023-02-05", 40.0),
        ("C", "2023-03-08", 5.0),
    ]
    df = pd.DataFrame(rows, columns=["customer_id", "order_date", "revenue"])
    df["order_date"] = pd.to_datetime(df["order_date"])
    return df


def test_cohort_retention_values() -> None:
    tidy = cohort_retention(tiny_tx())
    jan = tidy[tidy["cohort_month"].astype(str) == "2023-01-01"].set_index("month_index")
    # Jan cohort size = 2 (A, B). Month 0: both active -> 1.0. Month 1: only A -> 0.5.
    assert jan.loc[0, "cohort_size"] == 2
    assert jan.loc[0, "retention"] == pytest.approx(1.0)
    assert jan.loc[1, "active_customers"] == 1
    assert jan.loc[1, "retention"] == pytest.approx(0.5)

    feb = tidy[tidy["cohort_month"].astype(str) == "2023-02-01"].set_index("month_index")
    # Feb cohort size = 1 (C). Month 0 -> 1.0, month 1 -> 1.0.
    assert feb.loc[0, "cohort_size"] == 1
    assert feb.loc[1, "retention"] == pytest.approx(1.0)


def test_retention_matrix_shape() -> None:
    matrix = retention_matrix(tiny_tx())
    assert list(matrix.index.astype(str)) == ["2023-01-01", "2023-02-01"]
    # month 0 always fully retained
    assert (matrix[0] == 1.0).all()
    # Feb cohort has no month-2 observation -> NaN there for that row is fine.
    assert matrix.iloc[0][1] == pytest.approx(0.5)


def test_month_zero_always_full_retention() -> None:
    tx = generate_transactions(n_customers=200, n_months=8, seed=11)
    tidy = cohort_retention(tx)
    month0 = tidy[tidy["month_index"] == 0]
    assert (month0["retention"] == 1.0).all()
    assert (month0["active_customers"] == month0["cohort_size"]).all()


def test_retention_is_bounded() -> None:
    tx = generate_transactions(n_customers=300, n_months=10, seed=5)
    tidy = cohort_retention(tx)
    assert tidy["retention"].between(0.0, 1.0).all()


def test_revenue_by_cohort_values() -> None:
    rev = revenue_by_cohort(tiny_tx())
    jan = rev[rev["cohort_month"].astype(str) == "2023-01-01"].set_index("month_index")
    # Jan month 0 revenue = A(10) + B(30) = 40; month 1 = A(20) = 20.
    assert jan.loc[0, "revenue"] == pytest.approx(40.0)
    assert jan.loc[1, "revenue"] == pytest.approx(20.0)
    # revenue_per_customer = revenue / cohort_size (2)
    assert jan.loc[0, "revenue_per_customer"] == pytest.approx(20.0)


def test_revenue_total_matches_input() -> None:
    tx = generate_transactions(n_customers=150, n_months=7, seed=9)
    rev = revenue_by_cohort(tx)
    assert rev["revenue"].sum() == pytest.approx(tx["revenue"].sum(), rel=1e-6)


def test_rfm_scores_ranges_and_completeness() -> None:
    tx = generate_transactions(n_customers=400, n_months=10, seed=4)
    rfm = rfm_scores(tx, bins=5)
    assert rfm["customer_id"].nunique() == tx["customer_id"].nunique()
    for col in ("r_score", "f_score", "m_score"):
        assert rfm[col].between(1, 5).all()
    assert (rfm["recency"] >= 1).all()
    assert (rfm["frequency"] >= 1).all()
    # rfm_score is the concatenation of the three digit scores
    sample = rfm.iloc[0]
    assert sample["rfm_score"] == f"{sample.r_score}{sample.f_score}{sample.m_score}"


def test_rfm_recency_ordering() -> None:
    """A customer who bought more recently must not score worse on recency."""
    rows = [
        ("recent", "2023-06-01", 50.0),
        ("stale", "2023-01-01", 50.0),
    ]
    df = pd.DataFrame(rows, columns=["customer_id", "order_date", "revenue"])
    df["order_date"] = pd.to_datetime(df["order_date"])
    rfm = rfm_scores(df, bins=2).set_index("customer_id")
    recency = {str(k): int(v) for k, v in rfm["recency"].items()}
    r_score = {str(k): int(v) for k, v in rfm["r_score"].items()}
    assert recency["recent"] < recency["stale"]
    assert r_score["recent"] >= r_score["stale"]


def test_segment_summary_shares_sum_to_one() -> None:
    tx = generate_transactions(n_customers=500, n_months=12, seed=42)
    seg = segment_summary(tx)
    assert seg["revenue_share"].sum() == pytest.approx(1.0, abs=1e-3)
    assert seg["customers"].sum() == tx["customer_id"].nunique()
    # sorted by total_revenue descending
    assert seg["total_revenue"].is_monotonic_decreasing


def test_rfm_is_deterministic() -> None:
    """NTILE ties are broken by customer_id, so scores must not drift."""
    tx = generate_transactions(n_customers=350, n_months=9, seed=13)
    a = rfm_scores(tx)
    b = rfm_scores(tx)
    pd.testing.assert_frame_equal(a, b)
    # A second summary from the same data must match to the cent.
    pd.testing.assert_frame_equal(segment_summary(tx), segment_summary(tx))


def test_missing_columns_raises() -> None:
    bad = pd.DataFrame({"customer_id": [1], "amount": [5.0]})
    with pytest.raises(ValueError, match="missing required columns"):
        cohort_retention(bad)


def test_empty_raises() -> None:
    empty = pd.DataFrame(columns=["customer_id", "order_date", "revenue"])
    with pytest.raises(ValueError, match="empty"):
        revenue_by_cohort(empty)
