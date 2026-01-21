# cohortkit

**Retention analytics for any customer_id / order_date / revenue table - cohort triangles, RFM segments, and revenue-by-cohort - powered by in-process DuckDB. No warehouse, no network, no config.**

## Problem

Every subscription or e-commerce business needs the same three retention views:
a **cohort-retention triangle** (do customers acquired in March stick around?),
an **RFM segmentation** (who are my Champions vs. my At-Risk customers?), and
a **revenue-by-cohort** breakdown (which acquisition month is actually paying off?).
These usually live in a BI tool or a pile of copy-pasted SQL. cohortkit turns
them into three tidy-DataFrame function calls (and a CLI) that run entirely
in-process on top of DuckDB, so they work in a notebook, a test, or a cron job
with zero infrastructure.

## Install / quickstart

Requires [uv](https://docs.astral.sh/uv/). From a fresh clone:

```bash
uv sync                      # install duckdb + pandas into a local venv
uv run pytest -q             # 24 tests, all green
uv run cohortkit --help      # CLI entry point
```

### 30-second tour (no data of your own needed)

```bash
# 1. write a deterministic synthetic transactions file
uv run cohortkit generate --customers 800 --months 12 --seed 42 --out tx.csv

# 2. print the cohort-retention triangle
uv run cohortkit cohorts --input tx.csv --matrix

# 3. score every customer and roll up by segment
uv run cohortkit rfm      --input tx.csv --out rfm.csv
uv run cohortkit segments --input tx.csv
```

Every subcommand also works **without** --input: it generates the synthetic
table on the fly (--seed to vary it), so you can explore before wiring up real data.

## Library usage

```python
import cohortkit as ck

tx = ck.generate_transactions(n_customers=800, n_months=12, seed=42)
# 6527 transactions, 800 customers, $534,829.15 total revenue

triangle = ck.retention_matrix(tx)          # cohort_month x month_index -> retention
rfm      = ck.rfm_scores(tx)                 # per-customer R/F/M scores + segment
segments = ck.segment_summary(tx)           # per-segment customers + revenue share
revenue  = ck.revenue_by_cohort(tx)         # revenue contribution per cohort/month
```

### Real output: the cohort triangle

retention_matrix returns the classic retention triangle - rows are acquisition
months, columns are months-since-acquisition, cells are the fraction of the cohort
still active. Month 0 is always 1.0; the diagonal fades as cohorts age out of the
12-month window (empty cells = not yet observable).

```
month_index     0      1      2      3      4      5      6      7
cohort_month
2023-01-01    1.0  0.809  0.553  0.474  0.309  0.283  0.263  0.237
2023-02-01    1.0  0.767  0.612  0.411  0.403  0.333  0.240  0.124
2023-03-01    1.0  0.785  0.711  0.479  0.413  0.289  0.314  0.240
2023-04-01    1.0  0.738  0.699  0.466  0.417  0.291  0.272  0.233
2023-05-01    1.0  0.734  0.570  0.468  0.405  0.380  0.215  0.127
2023-06-01    1.0  0.760  0.587  0.453  0.333  0.373  0.267
```

Read across a row: the Jan-2023 cohort keeps **80.9%** of its customers in month 1,
but only **23.7%** by month 7 - the typical retention decay curve.

### Real output: RFM segments

segment_summary scores each customer 1-5 on Recency, Frequency and Monetary value
(DuckDB NTILE, ties broken by customer_id so results are byte-stable), maps them
to a named segment, and rolls up revenue:

```
           segment  customers  total_revenue  avg_monetary  revenue_share
         Champions        178      186013.15       1045.02         0.3478
             Loyal        142      131059.94        922.96         0.2451
              Lost        183       62467.97        341.36         0.1168
Potential Loyalist         89       55740.93        626.30         0.1042
           At Risk         71       47049.74        662.67         0.0880
               New         84       31537.57        375.45         0.0590
         Promising         53       20959.85        395.47         0.0392
```

The headline: **178 Champions (22% of customers) drive 34.8% of revenue** - the kind
of concentration that tells you where to spend retention budget.

> All numbers above come straight from generate_transactions(seed=42) and are
> re-checked on every CI run (see test_revenue_total_matches_input,
> test_segment_summary_shares_sum_to_one, test_rfm_is_deterministic). Nothing is
> hand-typed.

## API

| Function | Returns |
|---|---|
| generate_transactions(n_customers, n_months, start, seed, base_retention) | Synthetic tidy transactions (customer_id, order_date, revenue). Deterministic per seed. |
| cohort_retention(tx) | Long/tidy table: cohort_month, month_index, active_customers, cohort_size, retention. |
| retention_matrix(tx) | The tidy table pivoted into a cohort triangle. |
| revenue_by_cohort(tx) | cohort_month, month_index, revenue, cohort_size, revenue_per_customer. |
| rfm_scores(tx, snapshot_date=None, bins=5) | Per-customer recency/frequency/monetary, r/f/m_score, rfm_score, segment. |
| segment_summary(tx, **rfm_kwargs) | Per-segment customers, total_revenue, avg_monetary, revenue_share. |

Bring your own data by passing any DataFrame with the three required columns -
the synthetic generator is only a convenience for demos and tests.

## Development

```bash
uv run ruff check .          # lint (E,F,I,UP,B,SIM,RUF, line-length 100)
uv run mypy src tests        # strict type-check
uv run pytest -q             # tests
```

CI (.github/workflows/ci.yml) runs all three on every push and PR against Python 3.12.

## What I'd build next

- **Rolling / weekly cohorts** - a freq="W" option alongside the monthly default.
- **Survival curves** - fit and export a per-cohort retention decay model for forecasting LTV.
- **Cohort LTV** - cumulative revenue_per_customer with a payback-period column.
- **Parquet/SQL sources** - let the CLI read Parquet and query a live DuckDB/Postgres table, not just CSV.
- **A tiny HTML report** - render the triangle as a heatmap and the segments as a bar chart from one command.

## Maintainer

**Sai Chandra Vuddamari**
Research and Innovation Analyst
Email: sssaichandra375@gmail.com

I am a detail-oriented analyst focused on building structure out of critical thinking. I specialize in analyzing data through SQL, Python, and R to create accurate reporting systems and dashboards. With over 4 years of professional experience, I maintain this project to provide a streamlined, infrastructure-free approach to retention analytics.