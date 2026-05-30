"""Part 2 — minimum additional funds, minimality, and the two guardrails."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import _helpers as H  # noqa: E402
from feasibility.engine import evaluate_offer  # noqa: E402
from feasibility.models import load_case  # noqa: E402


def test_case2_exact_minima():
    client, offer, rules = load_case("cases/case2_infeasible_minima")
    r = evaluate_offer(client, offer, rules)
    af = r.additional_funds
    assert af.lump_sum.amount_cents == 10000
    assert af.lump_sum.within_guardrail is True
    assert af.monthly_increment.amount_cents == 2500
    assert af.monthly_increment.num_drafts == 5
    assert af.monthly_increment.within_guardrail is True


def test_lump_is_minimal_one_cent_less_is_infeasible():
    client, offer, rules = load_case("cases/case2_infeasible_minima")
    r = evaluate_offer(client, offer, rules)
    L = r.additional_funds.lump_sum.amount_cents
    when = r.additional_funds.lump_sum.date
    from feasibility.models import LedgerEntry
    from dataclasses import replace

    def feasible_with_lump(amount):
        led = list(client.ledger) + [LedgerEntry(when, amount, "credit")]
        return evaluate_offer(replace(client, ledger=led), offer, rules).feasible

    assert feasible_with_lump(L) is True
    assert feasible_with_lump(L - 1) is False


def test_increment_is_minimal_one_cent_less_is_infeasible():
    client, offer, rules = load_case("cases/case2_infeasible_minima")
    r = evaluate_offer(client, offer, rules)
    X = r.additional_funds.monthly_increment.amount_cents
    from feasibility.models import LedgerEntry
    from dataclasses import replace

    def feasible_with_inc(x):
        led = [
            LedgerEntry(e.date, e.amount_cents + x, e.type)
            if (e.type == "credit" and e.date > client.as_of_date)
            else e
            for e in client.ledger
        ]
        return evaluate_offer(replace(client, ledger=led), offer, rules).feasible

    assert feasible_with_inc(X) is True
    assert feasible_with_inc(X - 1) is False


def test_lump_and_increment_can_differ_and_hit_guardrails_independently():
    # 5 drafts of 10000, only 4 usable before the horizon; a large offer means
    # the lump (single early credit) stays within its 0.65*offer cap while the
    # per-draft increment blows past max(10000, 0.40*draft).
    client = H.mk_client(10000, 5, last="2026-05-01")
    offer = H.mk_offer(200000, pct=0.5)  # ot 100000
    rules = H.mk_rules(max_terms=4, max_payments=4)
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is False
    af = r.additional_funds
    # Shortfall is 60000 (offer 100000 vs 40000 usable).
    assert af.lump_sum.amount_cents == 60000
    assert af.lump_sum.within_guardrail is True  # 60000 <= round(0.65*100000)=65000
    assert af.monthly_increment.amount_cents == 15000  # 60000 / 4 usable drafts
    assert af.monthly_increment.within_guardrail is False  # 15000 > max(10000, 4000)
    assert af.monthly_increment.reason != ""


def test_lump_guardrail_rejection_reason_set():
    # One usable cadence date and a single small draft against a big offer makes
    # the shortfall exceed 0.65*offer_total, so the lump is rejected.
    client = H.mk_client(5000, 1, first="2026-01-01", last="2026-01-31")
    offer = H.mk_offer(40000, pct=0.5)  # ot 20000, lump cap = 13000
    rules = H.mk_rules(max_terms=1, max_payments=1, min_payment_cents=2500, max_segments=1)
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is False
    lump = r.additional_funds.lump_sum
    assert lump.amount_cents == 15000  # 20000 owed vs one 5000 draft
    assert lump.within_guardrail is False  # 15000 > 13000
    assert lump.reason != ""


def test_structurally_infeasible_no_funds_help():
    # offer_total below the base minimum payment -> no valid vector for any k,
    # and no amount of extra cash can fix that.
    client = H.mk_client(10000, 6, last="2026-07-01")
    offer = H.mk_offer(2000, pct=0.5)  # ot 1000 < min_payment 2500
    rules = H.mk_rules(min_payment_cents=2500)
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is False
    assert r.additional_funds.lump_sum.within_guardrail is False
    assert r.additional_funds.lump_sum.reason != ""
    assert r.additional_funds.monthly_increment.within_guardrail is False


def test_num_drafts_counts_all_future_drafts_even_unusable_ones():
    # The 5th draft (May 1) lands after the last usable cadence date (Apr 30),
    # yet num_drafts still counts all five future drafts.
    client, offer, rules = load_case("cases/case2_infeasible_minima")
    r = evaluate_offer(client, offer, rules)
    assert r.additional_funds.monthly_increment.num_drafts == 5
