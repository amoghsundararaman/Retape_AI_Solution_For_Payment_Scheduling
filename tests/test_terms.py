"""max_terms (months the plan may span) vs max_payments (creditor-payment count).

ASSIGNMENT.md flags these as currently redundant and invites distinct meanings.
We make max_payments cap the creditor payments and max_terms cap the total span
(creditor payments plus trailing fee-only months).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import _helpers as H  # noqa: E402
from feasibility.engine import evaluate_offer  # noqa: E402


def _big_fee_case():
    # ot 10000, program fee 100000 (huge) -> the fee needs several months of
    # collection beyond the 2 creditor-payment dates.
    client = H.mk_client(20000, 8, last="2026-08-31")
    offer = H.mk_offer(20000, original=400000, pct=0.5)
    return client, offer


def test_max_terms_limits_the_fee_only_tail():
    client, offer = _big_fee_case()
    narrow = H.mk_rules(max_terms=2, max_payments=2, max_segments=2, program_fee_pct=0.25)
    wide = H.mk_rules(max_terms=8, max_payments=2, max_segments=2, program_fee_pct=0.25)
    assert evaluate_offer(client, offer, narrow).feasible is False  # 2 months can't hold the fee
    assert evaluate_offer(client, offer, wide).feasible is True     # 8 months can


def test_max_payments_caps_creditor_payments_below_the_span():
    client, offer = _big_fee_case()
    wide = H.mk_rules(max_terms=8, max_payments=2, max_segments=2, program_fee_pct=0.25)
    r = evaluate_offer(client, offer, wide)
    pay_rows = [row for row in r.schedule if row.creditor_payment_cents > 0]
    fee_only = [row for row in r.schedule if row.creditor_payment_cents == 0 and row.program_fee_cents > 0]
    assert len(pay_rows) == 2          # capped by max_payments
    assert len(fee_only) >= 1          # the fee spills into fee-only months
