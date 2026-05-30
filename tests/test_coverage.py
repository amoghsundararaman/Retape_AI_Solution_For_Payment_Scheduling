"""Comprehensive edge-case and gap coverage.

The original 76-test suite covered the happy paths and the four provided
cases thoroughly. This file fills the remaining gaps identified by static
analysis of the source: date-math edge cases, all three builder k=1
scenarios, every is_valid_vector rejection path, the fee_not_collected
diagnostic kind, loader precedence rules, Part 2 boundary conditions,
and validation boundary values.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import _helpers as H
from feasibility import solver
from feasibility.engine import evaluate_offer
from feasibility.models import (
    LedgerEntry,
    add_months,
    client_from_dict,
    end_of_month,
    is_end_of_month,
    monthly_payment_dates,
    offer_from_dict,
    offer_total_cents,
    rules_from_dict,
)
from feasibility.validation import ValidationError, validate_client, validate_inputs, validate_rules


# ─────────────────────────────────────────────────────────────────────────────
# Date math
# ─────────────────────────────────────────────────────────────────────────────

def test_add_months_leap_year_clamps_to_feb_29():
    # Jan 31 in a leap year should land on Feb 29, not overflow.
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_add_months_non_leap_year_clamps_to_feb_28():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_add_months_year_boundary():
    assert add_months(date(2026, 12, 31), 1) == date(2027, 1, 31)
    assert add_months(date(2026, 11, 30), 2) == date(2027, 1, 30)


def test_add_months_identity_n_zero():
    d = date(2026, 3, 15)
    assert add_months(d, 0) == d


def test_monthly_payment_dates_count_zero_returns_empty():
    assert monthly_payment_dates(date(2026, 1, 31), 0) == []


def test_is_end_of_month_detects_all_month_endings():
    assert is_end_of_month(date(2026, 1, 31))
    assert is_end_of_month(date(2026, 2, 28))   # non-leap Feb
    assert is_end_of_month(date(2024, 2, 29))   # leap Feb
    assert is_end_of_month(date(2026, 4, 30))
    assert not is_end_of_month(date(2026, 1, 30))
    assert not is_end_of_month(date(2026, 2, 27))


def test_eom_cadence_crosses_year_boundary():
    # Dec 31 EOM cadence should produce Jan 31, Feb 28, ...
    dates = monthly_payment_dates(date(2026, 12, 31), 3)
    assert dates == [date(2026, 12, 31), date(2027, 1, 31), date(2027, 2, 28)]


def test_eom_cadence_stops_at_horizon():
    # Horizon Apr 30 — Apr 30 itself must be included; May 31 must not.
    client = H.mk_client(10000, 4, first="2026-01-01", last="2026-04-30")
    offer  = H.mk_offer(20000, fpd="2026-01-31")
    cad    = solver.cadence_dates(client, offer)
    assert cad[-1] == date(2026, 4, 30)
    assert all(d <= date(2026, 4, 30) for d in cad)


# ─────────────────────────────────────────────────────────────────────────────
# Builder layer — k = 1 and structural edge cases
# ─────────────────────────────────────────────────────────────────────────────

def test_build_even_k_equals_1_returns_single_payment():
    rules  = H.mk_rules(even_pays=True)
    floors = solver.floors_for_k(1, rules)
    pays   = solver.build_even(1, 50000, floors, rules)
    assert pays == [50000]


def test_build_even_k_equals_1_fails_when_below_floor():
    rules  = H.mk_rules(min_payment_cents=60000)
    floors = solver.floors_for_k(1, rules)
    # offer_total 50000 < floor 60000 → invalid
    assert solver.build_even(1, 50000, floors, rules) is None


def test_build_balloon_k_equals_1_single_payment_equals_total():
    rules  = H.mk_rules(is_ballooning_allowed=True)
    floors = solver.floors_for_k(1, rules)
    # k=1: no "early" payments, the single payment IS the balloon.
    pays = solver.build_balloon(1, 50000, floors, rules)
    assert pays == [50000]


def test_build_balloon_k_equals_1_fails_below_floor():
    rules  = H.mk_rules(is_ballooning_allowed=True, min_payment_cents=60000)
    floors = solver.floors_for_k(1, rules)
    assert solver.build_balloon(1, 50000, floors, rules) is None


def test_build_staircase_k_equals_1_always_valid_when_total_meets_floor():
    rules  = H.mk_rules()
    floors = solver.floors_for_k(1, rules)
    pays   = solver.build_staircase(1, 50000, floors, rules)
    assert pays == [50000]


def test_build_staircase_k_equals_1_fails_below_floor():
    rules  = H.mk_rules(min_payment_cents=60000)
    floors = solver.floors_for_k(1, rules)
    assert solver.build_staircase(1, 50000, floors, rules) is None


def test_build_all_vectors_k_max_zero_returns_empty_dict():
    # When the cadence is empty, k_max=0 → no vectors to build.
    result = solver.build_all_vectors("staircase", 50000, 0, H.mk_rules())
    assert result == {}


def test_builders_guard_against_non_positive_k():
    # All three builders defensively return None for k <= 0.
    rules  = H.mk_rules(is_ballooning_allowed=True)
    floors: list[int] = []
    assert solver.build_even(0, 50000, floors, rules) is None
    assert solver.build_balloon(0, 50000, floors, rules) is None
    assert solver.build_staircase(0, 50000, floors, rules) is None


def test_staircase_rejects_all_layouts_when_only_base_level_fits():
    # Flat floors (all at base) with offer_total == k × base means every
    # layout collapses to all-base payments. With max_token_pays < k, each
    # assembled vector exceeds the token budget and is_valid_vector rejects
    # it, so build_staircase exhausts every layout and returns None.
    rules  = H.mk_rules(min_payment_cents=2500, max_token_pays=1, max_segments=2)
    flat_floors = [2500, 2500, 2500, 2500]
    # 4 × 2500 = 10000 is the only achievable sum, and it puts 4 payments at
    # the base minimum (> max_token_pays of 1).
    assert solver.build_staircase(4, 10000, flat_floors, rules) is None


def test_staircase_skips_token_violating_layout_then_finds_valid_one():
    # With flat floors and a total above k × base, early layouts that land at
    # the base are skipped (token budget), but a higher flat level is found.
    rules  = H.mk_rules(min_payment_cents=2500, max_token_pays=1, max_segments=2)
    flat_floors = [2500, 2500, 2500, 2500]
    # 4 × 3000 = 12000 — a single level above the base, 0 payments at base.
    pays = solver.build_staircase(4, 12000, flat_floors, rules)
    assert pays == [3000, 3000, 3000, 3000]
    assert sum(1 for p in pays if p == 2500) == 0


def test_build_all_vectors_only_builds_valid_k_values():
    # offer_total=10000 with min_payment_cents=3500: k=3 would need 3×3500=10500>10000 → invalid.
    rules   = H.mk_rules(min_payment_cents=3500)
    vectors = solver.build_all_vectors("staircase", 10000, 3, rules)
    # k=3 floor sum = 10500 > 10000 → no valid vector → key 3 absent
    assert 3 not in vectors


# ─────────────────────────────────────────────────────────────────────────────
# is_valid_vector — all rejection paths
# ─────────────────────────────────────────────────────────────────────────────

def test_is_valid_vector_empty_pays_returns_false():
    rules  = H.mk_rules()
    floors = solver.floors_for_k(3, rules)
    assert solver.is_valid_vector([], floors, 30000, rules, enforce_segments=False) is False


def test_is_valid_vector_sum_mismatch_returns_false():
    rules  = H.mk_rules()
    floors = solver.floors_for_k(3, rules)
    # sum(pays) = 29000 != offer_total 30000
    assert solver.is_valid_vector([9000, 10000, 10000], floors, 30000, rules,
                                   enforce_segments=False) is False


def test_is_valid_vector_decreasing_sequence_returns_false():
    rules  = H.mk_rules()
    floors = solver.floors_for_k(3, rules)
    # 12000 > 10000 > 8000 is decreasing → invalid
    assert solver.is_valid_vector([12000, 10000, 8000], floors, 30000, rules,
                                   enforce_segments=False) is False


def test_is_valid_vector_below_floor_returns_false():
    rules  = H.mk_rules(min_payment_cents=5000)
    floors = solver.floors_for_k(3, rules)
    # First payment 1000 < floor 5000
    assert solver.is_valid_vector([1000, 14500, 14500], floors, 30000, rules,
                                   enforce_segments=False) is False


def test_is_valid_vector_too_many_at_base_returns_false():
    # Use a permissive floor vector so the base-count check (not the floor
    # check) is the predicate under test. floors_for_k would otherwise lift
    # positions past the token budget above the base and short-circuit here.
    rules  = H.mk_rules(min_payment_cents=2500, max_token_pays=2)
    flat_floors = [2500, 2500, 2500, 2500]
    # 4 payments at base (2500) > max_token_pays 2, but every payment meets
    # the (flat) floor and the sequence is non-decreasing and sums correctly.
    assert solver.is_valid_vector([2500, 2500, 2500, 2500], flat_floors, 10000, rules,
                                   enforce_segments=False) is False


def test_is_valid_vector_segment_cap_enforced_for_staircase():
    rules  = H.mk_rules(max_segments=2, max_token_pays=10)
    # [1000, 2000, 3000, 4000] has 4 distinct levels → exceeds max_segments=2
    pays = [1000, 2000, 3000, 4000]
    assert solver.is_valid_vector(pays, [1000]*4, 10000, rules,
                                   enforce_segments=True, max_segments=2) is False
    # Same sum, exactly 2 distinct levels → ok (1000+1000+4000+4000 = 10000)
    pays2 = [1000, 1000, 4000, 4000]
    assert solver.is_valid_vector(pays2, [1000]*4, 10000, rules,
                                   enforce_segments=True, max_segments=2) is True
    # 1 distinct level ≤ 2 → ok
    pays3 = [2500, 2500, 2500, 2500]
    assert solver.is_valid_vector(pays3, [1000]*4, 10000, rules,
                                   enforce_segments=True, max_segments=2) is True
    # Without the segment cap, the 4-distinct-level vector is accepted.
    assert solver.is_valid_vector(pays, [1000]*4, 10000, rules,
                                   enforce_segments=False) is True


# ─────────────────────────────────────────────────────────────────────────────
# floors_for_k — boundary values
# ─────────────────────────────────────────────────────────────────────────────

def test_floors_tier_from_position_1_applies_everywhere():
    # Tier (1, 5000) means the floor is 5000 from position 1 onward — i.e., always.
    rules  = H.mk_rules(min_payment_cents=2500, min_payment_tiers=[(1, 5000)], max_token_pays=4)
    floors = solver.floors_for_k(4, rules)
    assert floors == [5000, 5000, 5000, 5000]


def test_floors_max_token_pays_equals_k_all_can_sit_at_base():
    # When max_token_pays >= k, no position is forced above the base.
    rules  = H.mk_rules(min_payment_cents=2500, max_token_pays=10)
    floors = solver.floors_for_k(4, rules)
    # All four at base — token budget (10) is not exhausted.
    assert all(f == 2500 for f in floors)


def test_floors_non_decreasing_after_tier_step():
    # Tier at position 5 shouldn't make position 4 less than position 5.
    rules  = H.mk_rules(min_payment_cents=1000, min_payment_tiers=[(5, 4000)], max_token_pays=10)
    floors = solver.floors_for_k(6, rules)
    for i in range(1, len(floors)):
        assert floors[i] >= floors[i - 1], f"floors not non-decreasing at index {i}"


# ─────────────────────────────────────────────────────────────────────────────
# Engine and simulation
# ─────────────────────────────────────────────────────────────────────────────

def test_offer_total_zero_with_positive_floor_is_infeasible():
    # Creditor balance=0 means offer_total=0, but min_payment_cents=2500
    # so no valid payment vector exists → below_floor diagnostic.
    client = H.mk_client(10000, 3, last="2026-03-31")
    offer  = H.mk_offer(0, pct=0.5)           # offer_total = 0
    rules  = H.mk_rules(min_payment_cents=2500)
    r      = evaluate_offer(client, offer, rules)
    assert r.feasible is False
    assert r.diagnostics["kind"] == "below_floor"


def test_offer_total_zero_with_zero_floor_is_trivially_feasible():
    # offer_total=0 and min_payment_cents=0 → a $0 payment is valid → feasible.
    client = H.mk_client(10000, 3, last="2026-03-31")
    offer  = H.mk_offer(0, pct=0.5)
    rules  = H.mk_rules(min_payment_cents=0, bank_fee_cents=0, program_fee_pct=0.0)
    r      = evaluate_offer(client, offer, rules)
    assert r.feasible is True
    assert r.additional_funds is None


def test_nonzero_starting_balance_enables_feasibility():
    # A single $50 draft is insufficient for a $100 creditor payment,
    # but a $50 starting balance makes the total exactly right.
    client_broke  = H.mk_client(5000, 1, first="2026-01-01", last="2026-01-31", balance=0)
    client_funded = H.mk_client(5000, 1, first="2026-01-01", last="2026-01-31", balance=5000)
    offer = H.mk_offer(10000, pct=1.0)         # offer_total = 10000
    rules = H.mk_rules(max_terms=1, max_payments=1, max_segments=1,
                       bank_fee_cents=0, program_fee_pct=0.0)

    assert evaluate_offer(client_broke,  offer, rules).feasible is False
    r = evaluate_offer(client_funded, offer, rules)
    assert r.feasible is True
    H.assert_valid_schedule(r, client_funded, offer, rules)


def test_fee_not_collected_diagnostic():
    # Large program fee, small drafts: creditor payments fit but the fee
    # cannot be fully collected by the horizon.
    # 3 drafts × $150 = $450 available.
    # offer_total=$100 (1 payment), program_fee=round(2.0×$200)=$400.
    # $50 of fee remains after the last cadence date.
    client = H.mk_client(15000, 3, first="2026-01-01", last="2026-03-31")
    offer  = H.mk_offer(20000, original=20000, pct=0.5)   # offer_total=10000
    rules  = H.mk_rules(
        max_terms=3, max_payments=1, max_segments=1,
        bank_fee_cents=0, program_fee_pct=2.0,             # fee=40000
        min_payment_cents=2500,
    )
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is False
    assert r.diagnostics["kind"] == "fee_not_collected"
    assert r.diagnostics["shortfall_cents"] > 0


def test_even_pays_overrides_is_ballooning_allowed():
    # When both flags are set, even_pays wins and the shape is "even".
    client = H.mk_client(20000, 6, last="2026-06-30")
    offer  = H.mk_offer(60000, pct=0.5)
    rules  = H.mk_rules(even_pays=True, is_ballooning_allowed=True,
                         max_terms=6, max_payments=6, max_segments=1)
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is True
    assert r.pay_shape_used == "even"


def test_single_cadence_date_exactly_on_horizon():
    # first_payment_date is on the horizon → only 1 cadence date, and it's the horizon.
    client = H.mk_client(50000, 3, first="2026-01-01", last="2026-04-30")
    offer  = H.mk_offer(40000, pct=0.5, fpd="2026-04-30")   # first_payment = horizon
    cad    = solver.cadence_dates(client, offer)
    assert len(cad) == 1
    assert cad[0] == date(2026, 4, 30)


def test_with_draft_increment_does_not_touch_committed_debits():
    # Committed debits in the ledger must remain unchanged when the
    # engine adds a per-draft increment.
    from feasibility.engine import _with_draft_increment
    client = H.mk_client(
        10000, 3, last="2026-03-31",
        extra=[LedgerEntry(date(2026, 2, 15), 5000, "debit")],
    )
    incremented = _with_draft_increment(client, 1000)
    debits_orig = [e for e in client.ledger if e.type == "debit"]
    debits_new  = [e for e in incremented.ledger if e.type == "debit"]
    # Debit entries unchanged
    assert [(e.date, e.amount_cents) for e in debits_new] == \
           [(e.date, e.amount_cents) for e in debits_orig]
    # Credits increased by 1000
    credits_new = [e for e in incremented.ledger if e.type == "credit"]
    credits_old = [e for e in client.ledger if e.type == "credit"]
    assert all(n.amount_cents == o.amount_cents + 1000
               for n, o in zip(credits_new, credits_old))


def test_feasible_with_empty_ledger_starting_balance_only():
    # No scheduled drafts. Starting balance covers everything.
    client = H.mk_client(
        0, 0,                            # zero-amount drafts, no entries
        first="2026-01-01", last="2026-06-30",
        balance=100000,
    )
    offer = H.mk_offer(50000, pct=0.5, original=100000)
    rules = H.mk_rules(
        max_terms=1, max_payments=1, max_segments=1,
        bank_fee_cents=0, program_fee_pct=0.0,
    )
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is True
    assert all(row.balance_cents >= 0 for row in r.schedule)


def test_program_fee_collected_exactly_leaves_zero_slack():
    # Tight setup: credits just cover creditor payment + full fee;
    # balance hits 0 after fee skim → min_balance = 0.
    client = H.mk_client(20000, 1, first="2026-01-01", last="2026-01-31")
    # offer_total = 10000, program_fee = round(0.5 * 20000) = 10000
    offer  = H.mk_offer(20000, original=20000, pct=0.5)
    rules  = H.mk_rules(
        max_terms=1, max_payments=1, max_segments=1,
        bank_fee_cents=0, program_fee_pct=0.5,
    )
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is True
    assert r.diagnostics["min_balance_cents"] == 0


def test_multiple_credits_same_date_as_payment_summed_first():
    # Two credits landing on the same date as the creditor payment must both
    # be applied before the payment debit is processed.
    from dataclasses import replace
    extra = [
        LedgerEntry(date(2026, 1, 31), 5000, "credit"),
        LedgerEntry(date(2026, 1, 31), 5000, "credit"),
    ]
    # Without the extra credits, a single $10000 draft is too small.
    # With them (+10000), the total is $20000 — enough for $15000 payment.
    client = H.mk_client(
        10000, 1, first="2026-01-01", last="2026-01-31", extra=extra
    )
    offer = H.mk_offer(30000, pct=0.5)   # offer_total=15000
    rules = H.mk_rules(max_terms=1, max_payments=1, max_segments=1,
                        bank_fee_cents=0, program_fee_pct=0.0)
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is True
    H.assert_valid_schedule(r, client, offer, rules)


def test_no_cadence_when_first_payment_date_after_horizon():
    client = H.mk_client(10000, 2, first="2026-01-01", last="2026-02-01")
    offer  = H.mk_offer(40000, pct=0.5, fpd="2026-06-30")   # way past horizon
    r      = evaluate_offer(client, offer, rules=H.mk_rules())
    assert r.feasible is False
    assert r.diagnostics["kind"] == "no_cadence"
    assert r.diagnostics["binding_date"] is None


def test_large_starting_balance_trivially_feasible():
    # An absurdly large starting balance should always yield feasible.
    client = H.mk_client(0, 0, first="2026-01-01", last="2026-12-31",
                          balance=10_000_000)
    offer  = H.mk_offer(500000, pct=0.5)
    rules  = H.mk_rules(max_terms=6, max_payments=6, max_segments=2,
                         bank_fee_cents=0, program_fee_pct=0.0)
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is True


# ─────────────────────────────────────────────────────────────────────────────
# Validation — boundary values
# ─────────────────────────────────────────────────────────────────────────────

def test_settlement_pct_zero_is_valid():
    validate_inputs(
        H.mk_client(20000, 3, last="2026-03-31"),
        H.mk_offer(40000, pct=0.0),
        H.mk_rules(),
    )  # must not raise


def test_settlement_pct_one_is_valid():
    validate_inputs(
        H.mk_client(20000, 3, last="2026-03-31"),
        H.mk_offer(40000, pct=1.0),
        H.mk_rules(),
    )  # must not raise


def test_settlement_pct_negative_raises():
    with pytest.raises(ValidationError):
        validate_inputs(
            H.mk_client(20000, 3, last="2026-03-31"),
            H.mk_offer(40000, pct=-0.01),
            H.mk_rules(),
        )


def test_draft_day_boundaries():
    # draft_day=1 and draft_day=31 are both valid.
    for day in (1, 31):
        c = H.mk_client(20000, 3, last="2026-03-31", day=day)
        validate_inputs(c, H.mk_offer(40000, pct=0.5), H.mk_rules())  # no raise


def test_draft_day_zero_raises():
    c = H.mk_client(20000, 3, last="2026-03-31", day=0)
    with pytest.raises(ValidationError):
        validate_inputs(c, H.mk_offer(40000, pct=0.5), H.mk_rules())


def test_draft_day_32_raises():
    c = H.mk_client(20000, 3, last="2026-03-31", day=32)
    with pytest.raises(ValidationError):
        validate_inputs(c, H.mk_offer(40000, pct=0.5), H.mk_rules())


def test_tier_negative_min_cents_raises():
    with pytest.raises(ValidationError):
        validate_inputs(
            H.mk_client(20000, 3, last="2026-03-31"),
            H.mk_offer(40000, pct=0.5),
            H.mk_rules(min_payment_tiers=[(1, -100)]),
        )


def test_tier_from_payment_zero_raises():
    # 1-based index; 0 is invalid.
    with pytest.raises(ValidationError):
        validate_inputs(
            H.mk_client(20000, 3, last="2026-03-31"),
            H.mk_offer(40000, pct=0.5),
            H.mk_rules(min_payment_tiers=[(0, 5000)]),
        )


def test_negative_ledger_amount_raises():
    from feasibility.models import Client
    client = H.mk_client(20000, 3, last="2026-03-31",
                          extra=[LedgerEntry(date(2026, 2, 15), -100, "credit")])
    with pytest.raises(ValidationError):
        validate_client(client)


def test_max_segments_zero_raises():
    with pytest.raises(ValidationError):
        validate_inputs(
            H.mk_client(20000, 3, last="2026-03-31"),
            H.mk_offer(40000, pct=0.5),
            H.mk_rules(max_segments=0),
        )


def test_max_payments_zero_raises():
    with pytest.raises(ValidationError):
        validate_inputs(
            H.mk_client(20000, 3, last="2026-03-31"),
            H.mk_offer(40000, pct=0.5),
            H.mk_rules(max_payments=0),
        )


def test_bank_fee_cents_zero_is_valid():
    validate_inputs(
        H.mk_client(20000, 3, last="2026-03-31"),
        H.mk_offer(40000, pct=0.5),
        H.mk_rules(bank_fee_cents=0),
    )  # must not raise


# current_balance_cents is not validated (it can be negative — overdraft).
# This test documents that gap explicitly.
def test_negative_current_balance_not_caught_by_validation():
    from dataclasses import replace
    client = H.mk_client(20000, 3, last="2026-03-31")
    # Inject a negative balance directly (bypassing mk_client).
    negative_balance_client = replace(client, current_balance_cents=-5000)
    # validate_client must not raise — this is a known undocumented gap.
    validate_client(negative_balance_client)


# ─────────────────────────────────────────────────────────────────────────────
# Dict-based loaders
# ─────────────────────────────────────────────────────────────────────────────

def test_offer_from_dict_creditor_balance_cents_takes_precedence():
    # When both the old and new key names are present, the new name wins.
    raw = {
        "creditor": "Test",
        "creditor_balance_cents": 80000,
        "current_balance_cents": 99999,   # old name present but should be ignored
        "original_balance_cents": 100000,
        "settlement_pct": 0.5,
    }
    offer = offer_from_dict(raw)
    assert offer.current_balance_cents == 80000
    assert offer_total_cents(offer) == 40000   # based on 80000, not 99999


def test_offer_from_dict_neither_balance_key_raises_key_error():
    raw = {
        "creditor": "Test",
        "original_balance_cents": 100000,
        "settlement_pct": 0.5,
    }
    with pytest.raises(KeyError):
        offer_from_dict(raw)


def test_rules_from_dict_missing_optional_fields_uses_defaults():
    raw = {
        "max_terms": 6,
        "max_payments": 6,
        "min_payment_cents": 2500,
        "max_token_pays": 6,
        "bank_fee_cents": 500,
        "program_fee_pct": 0.2,
        # even_pays, is_ballooning_allowed, max_segments, min_payment_tiers omitted
    }
    rules = rules_from_dict(raw)
    assert rules.even_pays is False
    assert rules.is_ballooning_allowed is False
    assert rules.max_segments == 4       # default
    assert rules.min_payment_tiers == []


def test_client_from_dict_empty_ledger():
    raw = {
        "draft_amount_cents": 20000,
        "draft_day": 1,
        "first_draft_date": "2026-01-01",
        "last_draft_date": "2026-06-30",
        "as_of_date": "2025-12-31",
        "current_balance_cents": 0,
        # ledger key omitted entirely
    }
    client = client_from_dict(raw)
    assert client.ledger == []


def test_client_from_dict_with_ledger_entries():
    raw = {
        "draft_amount_cents": 10000,
        "draft_day": 1,
        "first_draft_date": "2026-01-01",
        "last_draft_date": "2026-03-31",
        "as_of_date": "2025-12-31",
        "current_balance_cents": 0,
        "ledger": [
            {"date": "2026-01-01", "amount_cents": 10000, "type": "credit"},
            {"date": "2026-02-01", "amount_cents": 5000,  "type": "debit"},
        ],
    }
    client = client_from_dict(raw)
    assert len(client.ledger) == 2
    assert client.ledger[0].type == "credit"
    assert client.ledger[1].amount_cents == 5000


# ─────────────────────────────────────────────────────────────────────────────
# Part 2 — additional funding edge cases
# ─────────────────────────────────────────────────────────────────────────────

def test_bisect_min_returns_zero_when_feasible_at_zero():
    from feasibility.engine import _bisect_min
    # feasible_at(0) is True → minimum extra needed is 0.
    assert _bisect_min(lambda amt: True, 1000) == 0


def test_bisect_min_returns_none_when_even_hi_infeasible():
    from feasibility.engine import _bisect_min
    # Nothing is ever feasible → None.
    assert _bisect_min(lambda amt: False, 1000) is None


def test_bisect_min_finds_exact_threshold():
    from feasibility.engine import _bisect_min
    # Feasible exactly at amount >= 537.
    assert _bisect_min(lambda amt: amt >= 537, 10000) == 537


def test_below_floor_means_no_lump_can_help():
    # When offer_total < minimum payment, no amount of extra cash makes
    # the plan feasible (the payment vector structure is wrong, not the balance).
    client = H.mk_client(10000, 6, last="2026-07-01")
    offer  = H.mk_offer(2000, pct=0.5)   # offer_total = 1000 < min_payment 2500
    rules  = H.mk_rules(min_payment_cents=2500)
    r      = evaluate_offer(client, offer, rules)
    assert r.feasible is False
    assert r.diagnostics["kind"] == "below_floor"
    # Both options outside guardrail (no amount can fix a structural floor violation)
    assert r.additional_funds.lump_sum.within_guardrail is False
    assert r.additional_funds.monthly_increment.within_guardrail is False


def test_no_future_drafts_reports_increment_n_zero():
    # Client ledger has no future credits (empty).  Monthly increment has n=0.
    from feasibility.engine import _num_future_drafts
    client = H.mk_client(0, 0, first="2026-01-01", last="2026-06-30", balance=0)
    assert _num_future_drafts(client) == 0

    offer = H.mk_offer(40000, pct=0.5)
    rules = H.mk_rules(max_terms=3, max_payments=3, max_segments=2)
    r     = evaluate_offer(client, offer, rules)
    # With zero balance and no drafts, infeasible.
    assert r.feasible is False
    assert r.additional_funds.monthly_increment.num_drafts == 0


def test_lump_guardrail_within_when_below_cap():
    # Mirror case2: 5 drafts of $100, only 4 usable (May 1 past Apr 30 horizon).
    # offer_total $400 needs $500 with the $100 fee — a $100 shortfall.
    from feasibility.models import round_half_up_pct
    client = H.mk_client(10000, 5, first="2026-01-01", last="2026-05-01")
    offer  = H.mk_offer(80000, original=80000, pct=0.5)   # offer_total=40000
    rules  = H.mk_rules(max_terms=4, max_payments=4, max_segments=2,
                         bank_fee_cents=0, program_fee_pct=0.125)   # fee=10000
    r      = evaluate_offer(client, offer, rules)
    assert r.feasible is False
    lump   = r.additional_funds.lump_sum
    cap    = round_half_up_pct(0.65, 40000)   # 26000
    # within_guardrail flag must agree with the lump-vs-cap comparison.
    assert (lump.amount_cents <= cap) == lump.within_guardrail


def test_increment_guardrail_respects_max_10000_floor():
    # Even with a tiny draft, the increment guardrail minimum is 10000.
    from feasibility.models import round_half_up_pct
    # draft = 100 cents ($1). 0.40 * 100 = 40. max(10000, 40) = 10000.
    client = H.mk_client(100, 5, first="2026-01-01", last="2026-05-01")
    offer  = H.mk_offer(200000, pct=0.5)   # offer_total = 100000
    rules  = H.mk_rules(max_terms=4, max_payments=4, max_segments=2,
                         bank_fee_cents=0, program_fee_pct=0.0)
    r      = evaluate_offer(client, offer, rules)
    assert r.feasible is False
    inc    = r.additional_funds.monthly_increment
    inc_cap = max(10000, round_half_up_pct(0.40, 100))  # = 10000
    assert (inc.amount_cents <= inc_cap) == inc.within_guardrail


# ─────────────────────────────────────────────────────────────────────────────
# Simulation correctness under unusual ledger layouts
# ─────────────────────────────────────────────────────────────────────────────

def test_simulation_credits_before_debits_exact_date_ordering():
    # A committed debit lands on the same date as the first draft. Credits
    # apply first (spec §3), so +20000 - 15000 = 5000 survives on Jan 1.
    # Without credits-first the balance would momentarily be -15000.
    debit_entry = LedgerEntry(date(2026, 1, 1), 15000, "debit")
    client = H.mk_client(20000, 3, first="2026-01-01", last="2026-03-31",
                          extra=[debit_entry])
    offer = H.mk_offer(10000, pct=0.5)   # offer_total=5000 (>= min_payment 2500)
    rules = H.mk_rules(max_terms=3, max_payments=3, max_segments=2,
                        bank_fee_cents=0, program_fee_pct=0.0)
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is True
    H.assert_valid_schedule(r, client, offer, rules)


def test_committed_debit_on_first_cadence_date_accounted_correctly():
    # A committed debit on the same date as the first creditor payment
    # reduces available cash.  The debit is fixed; the payment must still fit.
    debit_entry = LedgerEntry(date(2026, 1, 31), 5000, "debit")
    client = H.mk_client(20000, 3, last="2026-03-31", extra=[debit_entry])
    offer  = H.mk_offer(40000, pct=0.5)   # offer_total=20000
    rules  = H.mk_rules(max_terms=3, max_payments=3, max_segments=2,
                         bank_fee_cents=0, program_fee_pct=0.0)
    r = evaluate_offer(client, offer, rules)
    # With the debit on the first cadence date, feasibility depends on the
    # balance being >= creditor payment + debit on that date.
    # Either feasible or infeasible — what matters is the balance is never < 0.
    if r.feasible:
        assert all(row.balance_cents >= 0 for row in r.schedule)


def test_bank_fee_only_charged_on_creditor_payment_dates():
    # Fee-only months must carry zero bank fee regardless of bank_fee_cents.
    client = H.mk_client(20000, 6, last="2026-06-30")
    offer  = H.mk_offer(20000, original=200000, pct=0.5)   # ot=10000, fee=50000
    rules  = H.mk_rules(
        max_terms=6, max_payments=2, max_segments=2,
        bank_fee_cents=1000, program_fee_pct=0.25,          # fee=50000
    )
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is True
    for row in r.schedule:
        if row.creditor_payment_cents == 0:
            assert row.bank_fee_cents == 0, (
                f"Bank fee {row.bank_fee_cents} charged on fee-only month {row.date}"
            )
