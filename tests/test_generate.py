"""Tests for the deterministic synthetic data generator."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from cohortkit import generate_transactions


def test_schema_and_types() -> None:
    tx = generate_transactions(n_customers=50, n_months=6, seed=1)
    assert list(tx.columns) == ["customer_id", "order_date", "revenue"]
    assert pd.api.types.is_datetime64_any_dtype(tx["order_date"])
    assert pd.api.types.is_float_dtype(tx["revenue"])
    assert (tx["revenue"] > 0).all()


def test_deterministic_same_seed() -> None:
    a = generate_transactions(n_customers=100, n_months=8, seed=7)
    b = generate_transactions(n_customers=100, n_months=8, seed=7)
    pd.testing.assert_frame_equal(a, b)


def test_different_seed_differs() -> None:
    a = generate_transactions(n_customers=100, n_months=8, seed=7)
    b = generate_transactions(n_customers=100, n_months=8, seed=8)
    assert not a.equals(b)


def test_customer_count_and_window() -> None:
    tx = generate_transactions(n_customers=120, n_months=6, start=date(2022, 3, 1), seed=3)
    assert tx["customer_id"].nunique() == 120
    assert tx["order_date"].min() >= pd.Timestamp("2022-03-01")
    # 6 monthly cohorts => last activity within ~6 months of start.
    assert tx["order_date"].max() < pd.Timestamp("2022-09-01") + pd.Timedelta(days=31)


def test_sorted_by_date() -> None:
    tx = generate_transactions(n_customers=40, n_months=5, seed=2)
    assert tx["order_date"].is_monotonic_increasing


@pytest.mark.parametrize("kwargs", [{"n_customers": 0}, {"n_months": 0}, {"base_retention": 0.0}])
def test_invalid_args(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        generate_transactions(**kwargs)  # type: ignore[arg-type]
