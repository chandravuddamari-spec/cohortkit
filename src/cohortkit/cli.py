"""Command-line interface for cohortkit.

Examples:
    cohortkit generate --customers 800 --months 12 --out tx.csv
    cohortkit cohorts --input tx.csv --matrix
    cohortkit revenue --input tx.csv
    cohortkit rfm --input tx.csv
    cohortkit segments --input tx.csv

Any command that reads transactions accepts ``--input FILE.csv``; if omitted,
a deterministic synthetic table is generated on the fly (``--seed`` to vary).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import pandas as pd

from cohortkit import (
    generate_transactions,
    retention_matrix,
    revenue_by_cohort,
    rfm_scores,
    segment_summary,
)
from cohortkit.analytics import cohort_retention


def _load(args: argparse.Namespace) -> pd.DataFrame:
    """Return a transactions frame from --input or synthesize one."""
    if getattr(args, "input", None):
        frame = pd.read_csv(args.input, parse_dates=["order_date"])
        return frame
    return generate_transactions(
        n_customers=args.customers, n_months=args.months, seed=args.seed
    )


def _emit(frame: pd.DataFrame, out: str | None, index: bool = False) -> None:
    """Write ``frame`` to ``out`` as CSV or pretty-print to stdout."""
    if out:
        frame.to_csv(out, index=index)
        print(f"wrote {len(frame)} rows to {out}")
    else:
        with pd.option_context(
            "display.max_rows", 200, "display.width", 200, "display.max_columns", 30
        ):
            print(frame.to_string(index=index))


def _add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", help="transactions CSV (customer_id,order_date,revenue)")
    parser.add_argument("--customers", type=int, default=800, help="synthetic customers")
    parser.add_argument("--months", type=int, default=12, help="synthetic month window")
    parser.add_argument("--seed", type=int, default=42, help="synthetic PRNG seed")
    parser.add_argument("--out", help="write result to this CSV instead of stdout")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cohortkit", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate", help="write a synthetic transactions CSV")
    p_gen.add_argument("--customers", type=int, default=800)
    p_gen.add_argument("--months", type=int, default=12)
    p_gen.add_argument("--seed", type=int, default=42)
    p_gen.add_argument("--out", required=True, help="output CSV path")

    p_coh = sub.add_parser("cohorts", help="monthly cohort retention")
    _add_source_args(p_coh)
    p_coh.add_argument("--matrix", action="store_true", help="pivot into a cohort triangle")

    p_rev = sub.add_parser("revenue", help="revenue by cohort and month offset")
    _add_source_args(p_rev)

    p_rfm = sub.add_parser("rfm", help="per-customer RFM scores and segments")
    _add_source_args(p_rfm)

    p_seg = sub.add_parser("segments", help="per-segment rollup")
    _add_source_args(p_seg)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        frame = generate_transactions(
            n_customers=args.customers, n_months=args.months, seed=args.seed
        )
        _emit(frame, args.out)
        return 0

    transactions = _load(args)

    if args.command == "cohorts":
        if args.matrix:
            matrix = retention_matrix(transactions).round(3)
            _emit(matrix, args.out, index=True)
        else:
            _emit(cohort_retention(transactions), args.out)
    elif args.command == "revenue":
        _emit(revenue_by_cohort(transactions), args.out)
    elif args.command == "rfm":
        _emit(rfm_scores(transactions), args.out)
    elif args.command == "segments":
        _emit(segment_summary(transactions), args.out)
    else:  # pragma: no cover - argparse enforces choices
        parser.error(f"unknown command {args.command!r}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
