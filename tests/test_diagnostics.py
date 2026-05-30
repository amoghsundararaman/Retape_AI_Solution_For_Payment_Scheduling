"""Diagnostics: explain *why* infeasible, and report slack when feasible."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import _helpers as H  # noqa: E402
from feasibility.engine import evaluate_offer  # noqa: E402
from feasibility.models import load_case  # noqa: E402


def test_infeasible_diagnosis_pinpoints_first_negative_date():
    client, offer, rules = load_case("cases/case2_infeasible_minima")
    r = evaluate_offer(client, offer, rules)
    d = r.diagnostics
    assert d["kind"] == "balance_negative"
    assert d["binding_date"] == "2026-04-30"  # the last usable cadence date
    assert d["shortfall_cents"] == 10000      # matches the lump
    assert "negative" in d["reason"].lower()


def test_infeasible_diagnosis_below_floor():
    # offer_total below the base minimum -> no legal vector for any k.
    r = evaluate_offer(H.mk_client(10000, 6, last="2026-07-01"),
                       H.mk_offer(2000, pct=0.5), H.mk_rules(min_payment_cents=2500))
    assert r.diagnostics["kind"] == "below_floor"


def test_infeasible_diagnosis_no_cadence_when_first_payment_past_horizon():
    r = evaluate_offer(H.mk_client(10000, 2, last="2026-02-01"),
                       H.mk_offer(40000, pct=0.5, fpd="2026-06-30"), H.mk_rules())
    assert r.feasible is False
    assert r.diagnostics["kind"] == "no_cadence"


def test_feasible_diagnostics_report_slack():
    client, offer, rules = load_case("cases/case3_balloon")
    r = evaluate_offer(client, offer, rules)
    d = r.diagnostics
    assert "min_balance_cents" in d and "selected_k" in d
    true_min = min(row.balance_cents for row in r.schedule)
    assert d["min_balance_cents"] == true_min
    assert d["min_balance_cents"] >= 0
