"""Core retention analytics implemented as DuckDB SQL over a transactions table.

All public functions accept a tidy transactions ``pd.DataFrame`` with columns
``customer_id``, ``order_date`` and ``revenue`` and return tidy DataFrames.
DuckDB runs entirely in-process; nothing here touches the network or disk.
"""

from __future__ import annotations

import duckdb
import pandas as pd

REQUIRED_COLUMNS = ("customer_id", "order_date", "revenue")


def _validate(transactions: pd.DataFrame) -> pd.DataFrame:
    """Return a normalized copy of ``transactions`` or raise on bad input."""
    missing = [c for c in REQUIRED_COLUMNS if c not in transactions.columns]
    if missing:
        raise ValueError(f"transactions is missing required columns: {missing}")
    if transactions.empty:
        raise ValueError("transactions is empty")
    frame = transactions[list(REQUIRED_COLUMNS)].copy()
    frame["order_date"] = pd.to_datetime(frame["order_date"])
    return frame


def _connect(transactions: pd.DataFrame) -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB connection with ``tx`` registered."""
    con = duckdb.connect(":memory:")
    con.register("tx", _validate(transactions))
    return con


def cohort_retention(transactions: pd.DataFrame) -> pd.DataFrame:
    """Compute a tidy monthly cohort-retention table.

    A customer's cohort is the calendar month of their first order. For every
    (cohort_month, month_index) pair we count the distinct active customers and
    divide by the cohort size to get retention in ``[0, 1]``.

    Returns:
        Columns: ``cohort_month`` (date), ``month_index`` (int),
        ``active_customers`` (int), ``cohort_size`` (int), ``retention`` (float).
        Sorted by ``cohort_month`` then ``month_index``.
    """
    con = _connect(transactions)
    try:
        query = """
        WITH first_order AS (
            SELECT customer_id,
                   date_trunc('month', MIN(order_date)) AS cohort_month
            FROM tx
            GROUP BY customer_id
        ),
        activity AS (
            SELECT DISTINCT
                   f.cohort_month,
                   date_diff('month', f.cohort_month,
                             date_trunc('month', t.order_date)) AS month_index,
                   t.customer_id
            FROM tx t
            JOIN first_order f USING (customer_id)
        ),
        sizes AS (
            SELECT cohort_month, COUNT(*) AS cohort_size
            FROM first_order
            GROUP BY cohort_month
        ),
        counts AS (
            SELECT cohort_month, month_index,
                   COUNT(DISTINCT customer_id) AS active_customers
            FROM activity
            GROUP BY cohort_month, month_index
        )
        SELECT c.cohort_month,
               c.month_index,
               c.active_customers,
               s.cohort_size,
               c.active_customers::DOUBLE / s.cohort_size AS retention
        FROM counts c
        JOIN sizes s USING (cohort_month)
        ORDER BY c.cohort_month, c.month_index
        """
        result = con.execute(query).df()
    finally:
        con.close()
    result["cohort_month"] = pd.to_datetime(result["cohort_month"]).dt.date
    result["month_index"] = result["month_index"].astype(int)
    result["active_customers"] = result["active_customers"].astype(int)
    result["cohort_size"] = result["cohort_size"].astype(int)
    return result


def retention_matrix(transactions: pd.DataFrame) -> pd.DataFrame:
    """Pivot :func:`cohort_retention` into the classic cohort triangle.

    Rows are cohort months, columns are ``month_index`` offsets and cells hold
    retention fractions. Cells beyond a cohort's observation window are ``NaN``.
    """
    tidy = cohort_retention(transactions)
    matrix = tidy.pivot(index="cohort_month", columns="month_index", values="retention")
    matrix = matrix.sort_index()
    matrix.columns.name = "month_index"
    return matrix


def revenue_by_cohort(transactions: pd.DataFrame) -> pd.DataFrame:
    """Compute revenue contributed by each cohort at each month offset.

    Returns:
        Columns: ``cohort_month`` (date), ``month_index`` (int),
        ``revenue`` (float), ``cohort_size`` (int),
        ``revenue_per_customer`` (float, revenue / cohort_size).
        Sorted by ``cohort_month`` then ``month_index``.
    """
    con = _connect(transactions)
    try:
        query = """
        WITH first_order AS (
            SELECT customer_id,
                   date_trunc('month', MIN(order_date)) AS cohort_month
            FROM tx
            GROUP BY customer_id
        ),
        sizes AS (
            SELECT cohort_month, COUNT(*) AS cohort_size
            FROM first_order
            GROUP BY cohort_month
        ),
        rev AS (
            SELECT f.cohort_month,
                   date_diff('month', f.cohort_month,
                             date_trunc('month', t.order_date)) AS month_index,
                   SUM(t.revenue) AS revenue
            FROM tx t
            JOIN first_order f USING (customer_id)
            GROUP BY f.cohort_month, month_index
        )
        SELECT r.cohort_month,
               r.month_index,
               r.revenue,
               s.cohort_size,
               r.revenue / s.cohort_size AS revenue_per_customer
        FROM rev r
        JOIN sizes s USING (cohort_month)
        ORDER BY r.cohort_month, r.month_index
        """
        result = con.execute(query).df()
    finally:
        con.close()
    result["cohort_month"] = pd.to_datetime(result["cohort_month"]).dt.date
    result["month_index"] = result["month_index"].astype(int)
    result["cohort_size"] = result["cohort_size"].astype(int)
    result["revenue"] = result["revenue"].round(2)
    result["revenue_per_customer"] = result["revenue_per_customer"].round(2)
    return result


def rfm_scores(
    transactions: pd.DataFrame,
    snapshot_date: pd.Timestamp | str | None = None,
    bins: int = 5,
) -> pd.DataFrame:
    """Score every customer on Recency, Frequency and Monetary value.

    Each dimension is bucketed into ``bins`` quantiles via DuckDB ``NTILE`` so
    scores are ``1..bins`` with ``bins`` always being "best" (most recent, most
    frequent, highest spend). Customers are then mapped to a named segment.

    Args:
        transactions: Tidy transactions table.
        snapshot_date: "Today" for the recency calculation. Defaults to the day
            after the last order so the most recent buyer has recency ``1``.
        bins: Number of quantile buckets (default 5).

    Returns:
        Columns: ``customer_id``, ``recency`` (days, int), ``frequency`` (int),
        ``monetary`` (float), ``r_score``/``f_score``/``m_score`` (1..bins),
        ``rfm_score`` (str concatenation) and ``segment`` (str). Sorted by
        ``customer_id``.
    """
    if bins < 2:
        raise ValueError("bins must be >= 2")
    frame = _validate(transactions)
    if snapshot_date is None:
        snapshot = frame["order_date"].max() + pd.Timedelta(days=1)
    else:
        snapshot = pd.to_datetime(snapshot_date)

    con = duckdb.connect(":memory:")
    con.register("tx", frame)
    try:
        query = """
        WITH per_customer AS (
            SELECT customer_id,
                   date_diff('day', MAX(order_date), $snapshot::TIMESTAMP) AS recency,
                   COUNT(*) AS frequency,
                   SUM(revenue) AS monetary
            FROM tx
            GROUP BY customer_id
        ),
        scored AS (
            -- customer_id tiebreaks ties so NTILE bucketing is deterministic.
            SELECT customer_id, recency, frequency, monetary,
                   NTILE($bins) OVER (ORDER BY recency DESC, customer_id)  AS r_score,
                   NTILE($bins) OVER (ORDER BY frequency ASC, customer_id) AS f_score,
                   NTILE($bins) OVER (ORDER BY monetary ASC, customer_id)  AS m_score
            FROM per_customer
        )
        SELECT customer_id, recency, frequency, monetary,
               r_score, f_score, m_score,
               CONCAT(r_score::VARCHAR, f_score::VARCHAR, m_score::VARCHAR) AS rfm_score,
               CASE
                   WHEN r_score >= $bins - 1 AND f_score >= $bins - 1 THEN 'Champions'
                   WHEN f_score >= $bins - 1                          THEN 'Loyal'
                   WHEN r_score >= $bins - 1 AND f_score <= 2         THEN 'New'
                   WHEN r_score >= 3 AND f_score >= 3                 THEN 'Potential Loyalist'
                   WHEN r_score <= 2 AND f_score >= 3                 THEN 'At Risk'
                   WHEN r_score <= 2 AND f_score <= 2                 THEN 'Lost'
                   ELSE 'Promising'
               END AS segment
        FROM scored
        ORDER BY customer_id
        """
        result = con.execute(
            query, {"snapshot": snapshot.to_pydatetime(), "bins": bins}
        ).df()
    finally:
        con.close()
    result["recency"] = result["recency"].astype(int)
    result["frequency"] = result["frequency"].astype(int)
    result["monetary"] = result["monetary"].round(2)
    for col in ("r_score", "f_score", "m_score"):
        result[col] = result[col].astype(int)
    return result


def segment_summary(transactions: pd.DataFrame, **rfm_kwargs: object) -> pd.DataFrame:
    """Aggregate :func:`rfm_scores` into per-segment counts and revenue.

    Returns:
        Columns: ``segment``, ``customers`` (int), ``total_revenue`` (float),
        ``avg_monetary`` (float), ``revenue_share`` (float, 0..1). Sorted by
        ``total_revenue`` descending.
    """
    rfm = rfm_scores(transactions, **rfm_kwargs)  # type: ignore[arg-type]
    grouped = (
        rfm.groupby("segment")
        .agg(
            customers=("customer_id", "count"),
            total_revenue=("monetary", "sum"),
            avg_monetary=("monetary", "mean"),
        )
        .reset_index()
    )
    total = grouped["total_revenue"].sum()
    grouped["revenue_share"] = grouped["total_revenue"] / total
    grouped["total_revenue"] = grouped["total_revenue"].round(2)
    grouped["avg_monetary"] = grouped["avg_monetary"].round(2)
    grouped["revenue_share"] = grouped["revenue_share"].round(4)
    grouped = grouped.sort_values("total_revenue", ascending=False).reset_index(drop=True)
    return grouped
