"""The selection objective is a pluggable policy, not a hard-coded constant."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import _helpers as H  # noqa: E402
from feasibility import objectives  # noqa: E402
from feasibility.engine import evaluate_offer  # noqa: E402


def _diverging_case():
    # even-pays, large fee, non-zero bank fee. A smaller k is feasible but
    # front-loads the fee less; a larger k front-loads better but pays more
    # bank fees. So the two objectives must disagree on k.
    client = H.mk_client(20000, 6, last="2026-06-30")
    offer = H.mk_offer(48000, original=96000, pct=0.5)  # ot 24000, fee 24000
    rules = H.mk_rules(
        even_pays=True, max_terms=6, max_payments=6, max_segments=1,
        bank_fee_cents=1000, program_fee_pct=0.25,
    )
    return client, offer, rules


def _k_and_bank(r):
    k = sum(1 for row in r.schedule if row.creditor_payment_cents > 0)
    bank = sum(row.bank_fee_cents for row in r.schedule)
    return k, bank


def test_default_objective_front_loads_fee():
    client, offer, rules = _diverging_case()
    r = evaluate_offer(client, offer, rules)  # default == front_load_fee
    k, bank = _k_and_bank(r)
    assert (k, bank) == (6, 6000)


def test_min_bank_fees_objective_picks_fewer_payments():
    client, offer, rules = _diverging_case()
    r = evaluate_offer(client, offer, rules, objective=objectives.min_bank_fees)
    k, bank = _k_and_bank(r)
    assert (k, bank) == (2, 2000)  # cheaper on bank fees than the default's k=6


def test_alternate_objective_still_yields_a_valid_schedule():
    client, offer, rules = _diverging_case()
    r = evaluate_offer(client, offer, rules, objective=objectives.min_bank_fees)
    H.assert_valid_schedule(r, client, offer, rules)


def test_registry_exposes_named_objectives():
    assert set(objectives.REGISTRY) == {"front_load_fee", "min_bank_fees", "max_slack"}
    assert objectives.DEFAULT is objectives.front_load_fee


def test_max_slack_objective_yields_valid_schedule():
    client, offer, rules = _diverging_case()
    r = evaluate_offer(client, offer, rules, objective=objectives.max_slack)
    H.assert_valid_schedule(r, client, offer, rules)


def test_max_slack_key_prefers_larger_min_balance():
    # The max_slack key is (min_balance, fee_key, -k); a larger min_balance wins.
    class _Sim:
        def __init__(self, min_balance, fee_key, total_bank):
            self.min_balance = min_balance
            self.fee_key = fee_key
            self.total_bank = total_bank

    loose = objectives.max_slack(_Sim(5000, (0,), 0), k=3)
    tight = objectives.max_slack(_Sim(100, (0,), 0), k=3)
    assert loose > tight
