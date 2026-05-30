"""Shape-family behaviour: even / staircase / balloon, and the floor rules."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import _helpers as H  # noqa: E402
from feasibility import solver  # noqa: E402
from feasibility.engine import evaluate_offer  # noqa: E402


# --- even -------------------------------------------------------------------

def test_even_remainder_pushed_to_latest_payments():
    # offer_total 50000 over k=6 -> 8333 x4, 8334 x2 (remainder on the latest).
    floors = solver.floors_for_k(6, H.mk_rules(even_pays=True))
    pays = solver.build_even(6, 50000, floors, H.mk_rules(even_pays=True))
    assert pays == [8333, 8333, 8333, 8333, 8334, 8334]
    assert sum(pays) == 50000
    assert pays == sorted(pays)  # non-decreasing


def test_even_divisible_is_flat():
    floors = solver.floors_for_k(4, H.mk_rules(even_pays=True))
    assert solver.build_even(4, 40000, floors, H.mk_rules(even_pays=True)) == [10000] * 4


def test_even_rejects_k_violating_token_budget():
    # All-equal at exactly the base min with k beyond the token budget is invalid.
    rules = H.mk_rules(even_pays=True, min_payment_cents=2500, max_token_pays=3)
    floors = solver.floors_for_k(8, rules)
    # 8 payments of 2500 == 20000, but 8 > max_token_pays=3 at base -> rejected.
    assert solver.build_even(8, 20000, floors, rules) is None


def test_even_end_to_end_shape_label():
    client = H.mk_client(20000, 7, last="2026-07-01")
    offer = H.mk_offer(100000, original=120000, pct=0.5)  # ot 50000
    rules = H.mk_rules(
        even_pays=True, max_terms=6, max_payments=6, max_segments=1,
        bank_fee_cents=1000, program_fee_pct=0.25,  # fee 30000
    )
    r = evaluate_offer(client, offer, rules)
    H.assert_valid_schedule(r, client, offer, rules)
    assert r.pay_shape_used == "even"
    creditor = [row.creditor_payment_cents for row in r.schedule if row.creditor_payment_cents]
    assert len(set(creditor)) <= 2  # equal up to the remainder cent


# --- staircase --------------------------------------------------------------

def test_staircase_lexmin_two_levels():
    rules = H.mk_rules(max_segments=2)
    floors = solver.floors_for_k(4, rules)
    # lex-min: floors early, residual in the final level.
    assert solver.build_staircase(4, 20000, floors, rules) == [2500, 2500, 2500, 12500]


def test_staircase_respects_segment_cap_indivisible_needs_two_levels():
    one = H.mk_rules(max_segments=1)
    # Not divisible by k under a single level -> no 1-level vector for this k.
    assert solver.build_staircase(3, 10001, solver.floors_for_k(3, one), one) is None
    two = H.mk_rules(max_segments=2)
    pays = solver.build_staircase(3, 10001, solver.floors_for_k(3, two), two)
    assert pays == [2500, 2500, 5001]
    assert len(set(pays)) <= 2


def test_staircase_tier_floor_forces_late_step():
    # Tier from payment 7 onward must be >= 5000 (mirrors case4).
    rules = H.mk_rules(
        max_terms=12, max_payments=12, max_segments=2,
        min_payment_tiers=[(7, 5000)], max_token_pays=6,
    )
    floors = solver.floors_for_k(12, rules)
    assert floors[6:] == [5000] * 6
    pays = solver.build_staircase(12, 60000, floors, rules)
    assert pays == [2500] * 6 + [7500] * 6
    assert all(p >= 5000 for p in pays[6:])


def test_token_and_tier_floor_vector():
    rules = H.mk_rules(max_token_pays=3, min_payment_tiers=[(5, 4000)])
    floors = solver.floors_for_k(8, rules)
    # positions 1-3 at base; position 4 just above base (token budget spent);
    # positions 5-8 at the tier floor.
    assert floors == [2500, 2500, 2500, 2501, 4000, 4000, 4000, 4000]


# --- balloon ----------------------------------------------------------------

def test_balloon_floors_early_final_absorbs():
    rules = H.mk_rules(is_ballooning_allowed=True)
    floors = solver.floors_for_k(5, rules)
    pays = solver.build_balloon(5, 30000, floors, rules)
    assert pays == [2500, 2500, 2500, 2500, 20000]
    assert sum(pays) == 30000


def test_balloon_only_used_when_allowed():
    # Same numbers, ballooning disallowed -> staircase family instead.
    client = H.mk_client(10000, 7, last="2026-07-01", extra=[H.debit("2026-02-01", 15000)])
    offer = H.mk_offer(60000, pct=0.5)  # ot 30000
    allowed = H.mk_rules(is_ballooning_allowed=True, max_terms=6, max_payments=6)
    r1 = evaluate_offer(client, offer, allowed)
    assert r1.pay_shape_used == "balloon"

    disallowed = H.mk_rules(is_ballooning_allowed=False, max_terms=6, max_payments=6, max_segments=4)
    r2 = evaluate_offer(client, offer, disallowed)
    # Without ballooning the engine must not report a balloon shape.
    assert r2.pay_shape_used in (None, "staircase")


def test_balloon_infeasible_when_floors_exceed_total():
    rules = H.mk_rules(is_ballooning_allowed=True, min_payment_cents=2500)
    floors = solver.floors_for_k(5, rules)
    # 4 floors already sum to 10000 > offer_total 8000 -> no balloon vector.
    assert solver.build_balloon(5, 8000, floors, rules) is None
