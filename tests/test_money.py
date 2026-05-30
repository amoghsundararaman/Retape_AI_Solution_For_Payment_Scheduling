"""Money rounding and loader tolerance — the two scaffolding footguns."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))

import _helpers as H  # noqa: E402
from feasibility.models import (  # noqa: E402
    load_offer,
    offer_total_cents,
    program_fee_cents,
    round_half_up,
    round_half_up_pct,
)


def test_round_half_up_goes_away_from_zero():
    assert round_half_up(2.5) == 3
    assert round_half_up(3.5) == 4  # banker's rounding would give 4 here too
    assert round_half_up(0.5) == 1  # but here banker's gives 0
    assert round_half_up(2.4) == 2
    assert round_half_up(-2.5) == -3


def test_round_half_up_differs_from_builtin_on_half():
    # Document the actual divergence: builtin round() is half-to-even.
    assert round(0.5) == 0 and round_half_up(0.5) == 1
    assert round(2.5) == 2 and round_half_up(2.5) == 3


def test_pct_rounding_no_float_drift():
    # 0.5 * 12345 = 6172.5 -> half-up 6173 (builtin round would give 6172).
    assert round_half_up_pct(0.5, 12345) == 6173
    # A percentage that is ugly in binary float still rounds cleanly via Decimal.
    assert round_half_up_pct(0.1, 5) == 1  # 0.5 -> 1


def test_offer_total_and_fee_use_half_up():
    offer = H.mk_offer(12345, original=12345, pct=0.5)
    assert offer_total_cents(offer) == 6173
    rules = H.mk_rules(program_fee_pct=0.5)
    assert program_fee_cents(offer, rules) == 6173


def _write(tmp, name, obj):
    p = os.path.join(tmp, name)
    with open(p, "w") as f:
        json.dump(obj, f)
    return p


def test_load_offer_accepts_legacy_current_balance_cents():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, "offer.json", {
            "creditor": "Legacy",
            "current_balance_cents": 100000,
            "original_balance_cents": 120000,
            "settlement_pct": 0.5,
            "first_payment_date": "2026-01-31",
        })
        offer = load_offer(p)
        assert offer.current_balance_cents == 100000
        assert offer.creditor_balance_cents == 100000  # alias works
        assert offer_total_cents(offer) == 50000


def test_load_offer_accepts_renamed_creditor_balance_cents():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, "offer.json", {
            "creditor": "Renamed",
            "creditor_balance_cents": 80000,  # the spec's renamed field
            "original_balance_cents": 80000,
            "settlement_pct": 0.5,
            "first_payment_date": "2026-01-31",
        })
        offer = load_offer(p)
        assert offer.current_balance_cents == 80000
        assert offer.creditor_balance_cents == 80000
        assert offer.first_payment_date == date(2026, 1, 31)
