"""Tests for the cohortkit command-line interface."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from cohortkit.cli import main


def test_generate_writes_csv(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "tx.csv"
    rc = main(["generate", "--customers", "60", "--months", "6", "--seed", "1", "--out", str(out)])
    assert rc == 0
    assert out.exists()
    df = pd.read_csv(out)
    assert list(df.columns) == ["customer_id", "order_date", "revenue"]
    assert df["customer_id"].nunique() == 60


def test_cohorts_matrix_from_generated(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["cohorts", "--customers", "80", "--months", "6", "--seed", "2", "--matrix"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "cohort_month" in out
    assert "month_index" in out


def test_rfm_roundtrip_via_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tx = tmp_path / "tx.csv"
    assert main(["generate", "--customers", "100", "--months", "8", "--out", str(tx)]) == 0
    capsys.readouterr()  # clear
    out_csv = tmp_path / "rfm.csv"
    rc = main(["rfm", "--input", str(tx), "--out", str(out_csv)])
    assert rc == 0
    rfm = pd.read_csv(out_csv)
    assert {"r_score", "f_score", "m_score", "segment"}.issubset(rfm.columns)
    assert len(rfm) == 100


def test_segments_and_revenue_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["segments", "--customers", "120", "--months", "6", "--seed", "3"]) == 0
    seg_out = capsys.readouterr().out
    assert "segment" in seg_out
    assert main(["revenue", "--customers", "120", "--months", "6", "--seed", "3"]) == 0
    rev_out = capsys.readouterr().out
    assert "revenue_per_customer" in rev_out
