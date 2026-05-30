"""The validation layer is the data contract at the boundary."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import _helpers as H  # noqa: E402
from feasibility.models import load_case  # noqa: E402
from feasibility.validation import ValidationError, validate_inputs  # noqa: E402


def test_provided_cases_all_validate():
    for case in ("case1_feasible_even", "case2_infeasible_minima", "case3_balloon", "case4_tiers"):
        client, offer, rules = load_case(f"cases/{case}")
        validate_inputs(client, offer, rules)  # must not raise


def test_settlement_pct_out_of_range_raises():
    with pytest.raises(ValidationError):
        validate_inputs(H.mk_client(20000, 3, last="2026-03-31"),
                        H.mk_offer(40000, pct=1.5), H.mk_rules())


def test_draft_day_out_of_range_raises():
    bad = H.mk_client(20000, 3, last="2026-03-31", day=32)
    with pytest.raises(ValidationError):
        validate_inputs(bad, H.mk_offer(40000, pct=0.5), H.mk_rules())


def test_first_after_last_raises():
    bad = H.mk_client(20000, 1, first="2026-06-01", last="2026-01-01")
    with pytest.raises(ValidationError):
        validate_inputs(bad, H.mk_offer(40000, pct=0.5), H.mk_rules())


def test_malformed_tier_raises():
    with pytest.raises(ValidationError):
        validate_inputs(H.mk_client(20000, 3, last="2026-03-31"),
                        H.mk_offer(40000, pct=0.5),
                        H.mk_rules(min_payment_tiers=[(0, 5000)]))  # from_payment must be >= 1
