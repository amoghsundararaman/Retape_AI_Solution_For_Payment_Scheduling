"""Edge cases that the four provided cases don't exercise.

Each test pins behaviour I verified by hand, so a regression surfaces as a
concrete failure rather than a silent change.
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))

import _helpers as H  # noqa: E402
from feasibility import solver  # noqa: E402
from feasibility.engine import evaluate_offer  # noqa: E402
from feasibility.models import LedgerEntry  # noqa: E402


def test_multiple_committed_debits_same_date_are_summed():
    client = H.mk_client(
        20000, 6, last="2026-06-30",
        extra=[H.debit("2026-02-01", 3000), H.debit("2026-02-01", 2000)],
    )
    credit_on, debit_on = solver._ledger_flows(client, client.last_draft_date)
    assert debit_on[date(2026, 2, 1)] == 5000  # 3000 + 2000 aggregated
    r = evaluate_offer(client, H.mk_offer(40000, pct=0.5),
                       H.mk_rules(max_terms=6, max_payments=6, max_segments=2))
    H.assert_valid_schedule(r, client, H.mk_offer(40000, pct=0.5),
                            H.mk_rules(max_terms=6, max_payments=6, max_segments=2))


def test_debit_before_first_credit_places_lump_early_enough():
    # A committed debit lands before any draft; with no starting balance the
    # plan is infeasible, and the lump must be placed on/before that debit date.
    client = H.mk_client(
        2500, 3, first="2026-02-01", last="2026-04-01",
        extra=[H.debit("2026-01-15", 5000)],
    )
    offer = H.mk_offer(40000, pct=0.5)
    rules = H.mk_rules(max_terms=3, max_payments=3)
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is False
    assert r.additional_funds.lump_sum.date <= date(2026, 1, 15)


def test_ledger_entry_on_as_of_date_is_ignored():
    # An entry dated exactly on as_of_date is already baked into the balance.
    client = H.mk_client(
        20000, 3, last="2026-03-31",
        extra=[LedgerEntry(date(2025, 12, 31), 99999, "credit")],
    )
    credit_on, _ = solver._ledger_flows(client, client.last_draft_date)
    assert date(2025, 12, 31) not in credit_on


def test_pre_as_of_entry_not_reapplied_and_nonzero_start_balance():
    client = H.mk_client(
        20000, 3, last="2026-03-31", balance=5000,
        extra=[LedgerEntry(date(2025, 12, 1), 12345, "credit")],
    )
    credit_on, _ = solver._ledger_flows(client, client.last_draft_date)
    assert date(2025, 12, 1) not in credit_on
    assert client.current_balance_cents == 5000  # the as_of balance stands alone


def test_max_token_pays_zero_forces_all_above_base():
    floors = solver.floors_for_k(4, H.mk_rules(max_token_pays=0, min_payment_cents=2500))
    assert floors == [2501, 2501, 2501, 2501]


def test_tiers_out_of_order_and_overlapping_resolve_by_max():
    floors = solver.floors_for_k(
        8, H.mk_rules(min_payment_tiers=[(5, 4000), (3, 3000), (5, 3500)], max_token_pays=8)
    )
    # tier (5,3500) is dominated by (5,4000); (3,3000) applies from payment 3.
    assert floors == [2500, 2500, 3000, 3000, 4000, 4000, 4000, 4000]


def test_large_payment_count_staircase_stays_bounded():
    # Worst case for the layout enumeration: many payments at the full segment
    # budget. The composition count is sum_{m<=S} C(k-1, m-1) per k, so this is
    # the shape most likely to regress into a blow-up. Guard it with a generous
    # wall-clock ceiling and confirm the result is still a valid schedule.
    import time

    client = H.mk_client(20000, 30, last="2028-06-30")
    offer = H.mk_offer(300000, pct=0.5)
    rules = H.mk_rules(
        max_terms=30, max_payments=30, max_segments=4, min_payment_cents=1000
    )
    start = time.perf_counter()
    r = evaluate_offer(client, offer, rules)
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"search took {elapsed:.2f}s — possible complexity regression"
    H.assert_valid_schedule(r, client, offer, rules)


def test_committed_debit_after_horizon_is_ignored():
    # A large debit dated after the horizon falls outside the settlement window
    # and must not make the offer infeasible (documented assumption).
    client = H.mk_client(20000, 3, last="2026-03-31", extra=[H.debit("2026-09-01", 100000)])
    offer = H.mk_offer(40000, pct=0.5)
    rules = H.mk_rules(max_terms=3, max_payments=3, max_segments=2)
    r = evaluate_offer(client, offer, rules)
    assert r.feasible is True
    # The post-horizon debit never appears in the simulated flows.
    credit_on, debit_on = solver._ledger_flows(client, client.last_draft_date)
    assert date(2026, 9, 1) not in debit_on
