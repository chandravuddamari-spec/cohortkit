"""cohortkit: offline retention analytics over any transactions table.

Public API:
    generate_transactions  -- deterministic synthetic data
    cohort_retention       -- tidy monthly retention table
    retention_matrix       -- pivoted cohort triangle
    revenue_by_cohort      -- revenue contribution per cohort/month
    rfm_scores             -- per-customer RFM scores + segment
    segment_summary        -- per-segment rollup
"""

from __future__ import annotations

from cohortkit.analytics import (
    cohort_retention,
    retention_matrix,
    revenue_by_cohort,
    rfm_scores,
    segment_summary,
)
from cohortkit.generate import generate_transactions

__all__ = [
    "cohort_retention",
    "generate_transactions",
    "retention_matrix",
    "revenue_by_cohort",
    "rfm_scores",
    "segment_summary",
]

__version__ = "0.1.0"
