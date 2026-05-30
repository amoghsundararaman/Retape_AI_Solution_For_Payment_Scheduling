"""Batch pipeline: structured records per case, and the golden regression gate."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from pipeline.batch import check_goldens, evaluate_case, run_batch  # noqa: E402


def test_goldens_match_committed_expected():
    # The deterministic-eval gate: every case's output equals its expected.json.
    assert check_goldens(Path("cases")) == 0


def test_batch_emits_one_record_per_case_with_expected_fields():
    records = run_batch(Path("cases"))
    assert len(records) == 4
    by_case = {r["case"]: r for r in records}
    assert set(by_case) == {
        "case1_feasible_even", "case2_infeasible_minima", "case3_balloon", "case4_tiers",
    }
    for rec in records:
        assert set(rec) >= {"case", "feasible", "pay_shape_used", "elapsed_ms", "result"}
        assert isinstance(rec["elapsed_ms"], float)


def test_record_verdicts_are_correct():
    by_case = {r["case"]: r for r in run_batch(Path("cases"))}
    assert by_case["case1_feasible_even"]["pay_shape_used"] == "even"
    assert by_case["case3_balloon"]["pay_shape_used"] == "balloon"
    assert by_case["case4_tiers"]["pay_shape_used"] == "staircase"
    assert by_case["case2_infeasible_minima"]["feasible"] is False
    assert by_case["case2_infeasible_minima"]["lump_cents"] == 10000


def test_single_case_record_includes_full_serialized_result():
    rec = evaluate_case(Path("cases/case1_feasible_even"))
    assert rec["result"]["feasible"] is True
    assert rec["result"]["schedule"] is not None
