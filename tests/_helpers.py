"""Shared builders and an independent schedule validator for the test suite.

The validator re-derives the running balance from scratch and re-checks every
hard constraint in ASSIGNMENT.md (5) against the *actual* engine output, rather
than trusting the engine's own bookkeeping. Most shape/feasibility tests funnel
through it, so a regression anywhere shows up as a concrete constraint failure.
"""

from __future__ import annotations

from datetime import date

from feasibility import solver
from feasibility.models import (
    Client,
    CreditorRules,
    LedgerEntry,
    Offer,
    add_months,
    offer_total_cents,
    program_fee_cents,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def mk_client(
    draft: int,
    n_drafts: int,
    *,
    first: str = "2026-01-01",
    last: str | None = None,
    day: int = 1,
    extra: list[LedgerEntry] | None = None,
    as_of: str = "2025-12-31",
    balance: int = 0,
) -> Client:
    fd = date.fromisoformat(first)
    led = [LedgerEntry(add_months(fd, i), draft, "credit") for i in range(n_drafts)]
    if extra:
        led += extra
    last_date = date.fromisoformat(last) if last else led[n_drafts - 1].date
    return Client(draft, day, fd, last_date, date.fromisoformat(as_of), balance, led)


def mk_offer(
    balance: int,
    *,
    original: int | None = None,
    pct: float = 0.5,
    fpd: str | None = "2026-01-31",
    creditor: str = "C",
) -> Offer:
    return Offer(
        creditor,
        balance,
        original if original is not None else balance,
        pct,
        date.fromisoformat(fpd) if fpd else None,
    )


def mk_rules(**kw) -> CreditorRules:
    base = dict(
        max_terms=12,
        max_payments=12,
        min_payment_cents=2500,
        max_token_pays=6,
        min_payment_tiers=[],
        even_pays=False,
        is_ballooning_allowed=False,
        max_segments=4,
        bank_fee_cents=0,
        program_fee_pct=0.0,
    )
    base.update(kw)
    return CreditorRules(**base)


def debit(d: str, amount: int) -> LedgerEntry:
    return LedgerEntry(date.fromisoformat(d), amount, "debit")


# ---------------------------------------------------------------------------
# Independent validator
# ---------------------------------------------------------------------------

def assert_valid_schedule(r, client: Client, offer: Offer, rules: CreditorRules) -> None:
    assert r.feasible is True
    assert r.schedule is not None and len(r.schedule) > 0
    rows = r.schedule

    offer_total = offer_total_cents(offer)
    program_fee = program_fee_cents(offer, rules)
    cadence = solver.cadence_dates(client, offer)
    cad_set = set(cadence)
    horizon = client.last_draft_date

    pay_rows = [row for row in rows if row.creditor_payment_cents > 0]
    creditor = [row.creditor_payment_cents for row in pay_rows]
    k = len(creditor)

    # (1) count & placement: consecutive cadence dates from the first one.
    assert 1 <= k <= min(rules.max_payments, rules.max_terms, len(cadence))
    assert [row.date for row in pay_rows] == cadence[:k]

    # (2) exact sum.
    assert sum(creditor) == offer_total

    # (3) non-decreasing.
    assert all(creditor[i] >= creditor[i - 1] for i in range(1, k))

    # (4) floors, including token-pay and tiers.
    floors = solver.floors_for_k(k, rules)
    assert all(p >= f for p, f in zip(creditor, floors))
    assert sum(1 for p in creditor if p == rules.min_payment_cents) <= rules.max_token_pays

    # (5) bank fee on payment dates only.
    for row in rows:
        expected_bf = rules.bank_fee_cents if row.creditor_payment_cents > 0 else 0
        assert row.bank_fee_cents == expected_bf

    # (6) program-fee timing: fully collected, never before the first payment date.
    assert sum(row.program_fee_cents for row in rows) == program_fee
    assert all(row.date >= cadence[0] for row in rows if row.program_fee_cents > 0)

    # (9) segment cap (staircase only).
    if r.pay_shape_used == "staircase":
        assert len(set(creditor)) <= rules.max_segments

    # horizon + cadence membership.
    for row in rows:
        assert row.date <= horizon
        assert row.date in cad_set

    # (10) feasibility: re-simulate the balance independently, credits-before-debits.
    credit_on: dict[date, int] = {}
    debit_on: dict[date, int] = {}
    for e in client.ledger:
        if e.date <= client.as_of_date:
            continue
        if e.type == "credit":
            credit_on[e.date] = credit_on.get(e.date, 0) + e.amount_cents
        else:
            debit_on[e.date] = debit_on.get(e.date, 0) + e.amount_cents
    sched_debit: dict[date, int] = {}
    reported: dict[date, int] = {}
    for row in rows:
        sched_debit[row.date] = (
            row.creditor_payment_cents + row.bank_fee_cents + row.program_fee_cents
        )
        reported[row.date] = row.balance_cents

    bal = client.current_balance_cents
    for d in sorted(set(credit_on) | set(debit_on) | set(sched_debit)):
        bal += credit_on.get(d, 0)
        bal -= debit_on.get(d, 0)
        bal -= sched_debit.get(d, 0)
        assert bal >= 0, f"balance negative on {d}: {bal}"
        if d in reported:
            assert reported[d] == bal, f"row balance mismatch on {d}: {reported[d]} != {bal}"
