"""Every feasible provided case must satisfy the full constraint validator."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import _helpers as H  # noqa: E402
from feasibility.engine import evaluate_offer  # noqa: E402
from feasibility.models import load_case  # noqa: E402


def _run(case: str):
    client, offer, rules = load_case(f"cases/{case}")
    return client, offer, rules, evaluate_offer(client, offer, rules)


def test_case1_schedule_is_fully_valid():
    client, offer, rules, r = _run("case1_feasible_even")
    H.assert_valid_schedule(r, client, offer, rules)
    assert r.pay_shape_used == "even"


def test_case3_schedule_is_fully_valid():
    client, offer, rules, r = _run("case3_balloon")
    H.assert_valid_schedule(r, client, offer, rules)
    assert r.pay_shape_used == "balloon"


def test_case4_schedule_is_fully_valid():
    client, offer, rules, r = _run("case4_tiers")
    H.assert_valid_schedule(r, client, offer, rules)
    assert r.pay_shape_used == "staircase"


def test_case2_infeasible_has_no_schedule():
    _, _, _, r = _run("case2_infeasible_minima")
    assert r.feasible is False
    assert r.schedule is None
    assert r.pay_shape_used is None
    assert r.additional_funds is not None


def test_serialized_shapes_match_spec():
    # Feasible: schedule present, additional_funds null.
    _, _, _, r1 = _run("case1_feasible_even")
    d1 = r1.to_dict()
    assert d1["feasible"] is True
    assert d1["additional_funds"] is None
    assert isinstance(d1["schedule"], list)
    row = d1["schedule"][0]
    assert set(row) == {
        "date",
        "creditor_payment_cents",
        "program_fee_cents",
        "bank_fee_cents",
        "balance_cents",
    }
    # Infeasible: schedule null, additional_funds populated with both options.
    _, _, _, r2 = _run("case2_infeasible_minima")
    d2 = r2.to_dict()
    assert d2["schedule"] is None
    af = d2["additional_funds"]
    assert "amount_cents" in af["lump_sum"] and "date" in af["lump_sum"]
    assert "amount_cents" in af["monthly_increment"] and "num_drafts" in af["monthly_increment"]
