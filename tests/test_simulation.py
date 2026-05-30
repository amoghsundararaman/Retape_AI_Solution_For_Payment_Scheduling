"""Date-by-date simulation: ordering, exact-zero, horizon, fee timing, cadence."""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))

import _helpers as H  # noqa: E402
from feasibility import solver  # noqa: E402
from feasibility.engine import evaluate_offer  # noqa: E402
from feasibility.models import default_first_payment_date, monthly_payment_dates  # noqa: E402


def test_same_day_credits_before_debits_and_exact_zero():
    # case3 shape: a same-day +10000 credit and -15000 committed debit on Feb 1
    # must net using credits first; the schedule rides the balance down to 0.
    client = H.mk_client(10000, 7, last="2026-07-01", extra=[H.debit("2026-02-01", 15000)])
    offer = H.mk_offer(60000, pct=0.5)
    rules = H.mk_rules(is_ballooning_allowed=True, max_terms=6, max_payments=6)
    r = evaluate_offer(client, offer, rules)
    H.assert_valid_schedule(r, client, offer, rules)
    # At least one row sits at exactly zero (the balance is genuinely tight).
    assert any(row.balance_cents == 0 for row in r.schedule)


def test_balance_never_negative_under_committed_debit():
    client = H.mk_client(10000, 7, last="2026-07-01", extra=[H.debit("2026-02-01", 15000)])
    offer = H.mk_offer(60000, pct=0.5)
    rules = H.mk_rules(is_ballooning_allowed=True, max_terms=6, max_payments=6)
    r = evaluate_offer(client, offer, rules)
    assert all(row.balance_cents >= 0 for row in r.schedule)


def test_horizon_excludes_dates_past_last_draft():
    # first_payment Jan31 EOM cadence; horizon May 1 -> only 4 cadence dates.
    client = H.mk_client(10000, 5, last="2026-05-01")
    offer = H.mk_offer(80000, pct=0.5)
    cad = solver.cadence_dates(client, offer)
    assert cad == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    assert all(d <= client.last_draft_date for d in cad)


def test_cadence_date_on_horizon_is_allowed():
    # Horizon exactly on a cadence date -> that date is usable.
    client = H.mk_client(50000, 4, last="2026-04-30")
    offer = H.mk_offer(40000, pct=0.5)  # ot 20000
    cad = solver.cadence_dates(client, offer)
    assert cad[-1] == date(2026, 4, 30) == client.last_draft_date
    r = evaluate_offer(client, offer, H.mk_rules(max_segments=2))
    H.assert_valid_schedule(r, client, offer, H.mk_rules(max_segments=2))


def test_program_fee_uses_fee_only_months_after_payments_end():
    # max_payments caps creditor payments at 2, but max_terms lets the plan span
    # 6 months -> the large fee spills onto later fee-only cadence dates, which
    # carry NO bank fee. This exercises the max_terms vs max_payments distinction.
    client = H.mk_client(20000, 6, last="2026-06-30")
    offer = H.mk_offer(20000, original=200000, pct=0.5)  # ot 10000, fee large
    rules = H.mk_rules(
        max_terms=6, max_payments=2, max_segments=2,
        bank_fee_cents=1000, program_fee_pct=0.25,  # fee 50000
    )
    r = evaluate_offer(client, offer, rules)
    H.assert_valid_schedule(r, client, offer, rules)
    fee_only = [row for row in r.schedule if row.creditor_payment_cents == 0 and row.program_fee_cents > 0]
    assert fee_only, "expected at least one fee-only month"
    assert all(row.bank_fee_cents == 0 for row in fee_only)


def test_no_program_fee_before_first_payment_date():
    client = H.mk_client(20000, 7, last="2026-07-01")
    offer = H.mk_offer(100000, original=120000, pct=0.5)
    rules = H.mk_rules(
        even_pays=True, max_terms=6, max_payments=6, max_segments=1,
        bank_fee_cents=1000, program_fee_pct=0.25,
    )
    r = evaluate_offer(client, offer, rules)
    first_pay = r.schedule[0].date
    assert all(row.date >= first_pay for row in r.schedule if row.program_fee_cents > 0)


def test_default_first_payment_date_is_eom_of_first_draft():
    client = H.mk_client(20000, 6, first="2026-03-10", last="2026-08-31")
    offer = H.mk_offer(60000, pct=0.5, fpd=None)  # omitted -> EOM default
    assert default_first_payment_date(client) == date(2026, 3, 31)
    assert solver.cadence_dates(client, offer)[0] == date(2026, 3, 31)


def test_midmonth_cadence_preserves_day():
    assert monthly_payment_dates(date(2026, 1, 15), 3) == [
        date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)
    ]


def test_eom_cadence_clamps_short_months():
    assert monthly_payment_dates(date(2026, 1, 31), 4) == [
        date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)
    ]


def test_single_payment_k1():
    # One draft big enough to cover a single creditor payment + fee.
    client = H.mk_client(60000, 1, last="2026-01-31")
    offer = H.mk_offer(80000, original=40000, pct=0.5)  # ot 40000
    rules = H.mk_rules(max_terms=1, max_payments=1, max_segments=1, program_fee_pct=0.25)  # fee 10000
    r = evaluate_offer(client, offer, rules)
    H.assert_valid_schedule(r, client, offer, rules)
    creditor = [row.creditor_payment_cents for row in r.schedule if row.creditor_payment_cents]
    assert creditor == [40000]
