from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from feasibility import solver
from feasibility.objectives import DEFAULT as DEFAULT_OBJECTIVE
from feasibility.models import (
    Client,
    CreditorRules,
    LedgerEntry,
    Offer,
    offer_total_cents,
    program_fee_cents,
    round_half_up_pct,
)


@dataclass
class ScheduleRow:
    date: date
    creditor_payment_cents: int
    program_fee_cents: int
    bank_fee_cents: int
    balance_cents: int


@dataclass
class FundsOption:
    amount_cents: int
    within_guardrail: bool
    reason: str
    date: date | None = None
    num_drafts: int | None = None


@dataclass
class AdditionalFunds:
    lump_sum: FundsOption
    monthly_increment: FundsOption


@dataclass
class Result:
    feasible: bool
    pay_shape_used: str | None = None
    schedule: list[ScheduleRow] | None = None
    additional_funds: AdditionalFunds | None = None
    diagnostics: dict | None = None

    def to_dict(self) -> dict:
        out: dict = {"feasible": self.feasible, "pay_shape_used": self.pay_shape_used}
        out["schedule"] = (
            [
                {
                    "date": r.date.isoformat(),
                    "creditor_payment_cents": r.creditor_payment_cents,
                    "program_fee_cents": r.program_fee_cents,
                    "bank_fee_cents": r.bank_fee_cents,
                    "balance_cents": r.balance_cents,
                }
                for r in self.schedule
            ]
            if self.schedule is not None
            else None
        )
        if self.additional_funds is None:
            out["additional_funds"] = None
        else:
            def opt(o: FundsOption) -> dict:
                d = {
                    "amount_cents": o.amount_cents,
                    "within_guardrail": o.within_guardrail,
                    "reason": o.reason,
                }
                if o.date is not None:
                    d["date"] = o.date.isoformat()
                if o.num_drafts is not None:
                    d["num_drafts"] = o.num_drafts
                return d

            out["additional_funds"] = {
                "lump_sum": opt(self.additional_funds.lump_sum),
                "monthly_increment": opt(self.additional_funds.monthly_increment),
            }
        out["diagnostics"] = self.diagnostics
        return out


def _shape_family(rules: CreditorRules) -> str:
    if rules.even_pays:
        return "even"
    if rules.is_ballooning_allowed:
        return "balloon"
    return "staircase"


def _best_schedule(client, rules, cadence, span, program_fee, vectors, objective):
    best = None
    for k, pays in vectors.items():
        sim = solver.simulate(client, rules, cadence, span, k, pays, program_fee, ScheduleRow)
        if not sim.feasible:
            continue
        key = objective(sim, k)
        if best is None or key > best[0]:
            best = (key, sim.rows, sim, k)
    if best is None:
        return None, None, None
    return best[1], best[2], best[3]


def _is_feasible(client, rules, cadence, span, program_fee, vectors) -> bool:
    for k, pays in vectors.items():
        if solver.simulate(client, rules, cadence, span, k, pays, program_fee, ScheduleRow).feasible:
            return True
    return False


def _with_extra_credit(client: Client, when: date, amount: int) -> Client:
    return replace(client, ledger=list(client.ledger) + [LedgerEntry(when, amount, "credit")])


def _with_draft_increment(client: Client, x: int) -> Client:
    led = [
        LedgerEntry(e.date, e.amount_cents + x, e.type)
        if (e.type == "credit" and e.date > client.as_of_date)
        else e
        for e in client.ledger
    ]
    return replace(client, ledger=led)


def _num_future_drafts(client: Client) -> int:
    return sum(1 for e in client.ledger if e.type == "credit" and e.date > client.as_of_date)


def _bisect_min(feasible_at, hi: int) -> int | None:
    """Smallest non-negative integer where feasible_at flips True.

    Safe to binary-search because feasibility is monotone in money —
    extra cash never makes a working plan infeasible.
    """
    if feasible_at(0):
        return 0
    if not feasible_at(hi):
        return None
    lo = 0
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if feasible_at(mid):
            hi = mid
        else:
            lo = mid
    return hi


def _funds_upper_bound(client, rules, cadence, offer_total, program_fee) -> int:
    committed = sum(
        e.amount_cents
        for e in client.ledger
        if e.type == "debit" and client.as_of_date < e.date <= client.last_draft_date
    )
    return offer_total + program_fee + rules.bank_fee_cents * len(cadence) + committed + 1


def _earliest_credit_date(client: Client) -> date:
    future = [e.date for e in client.ledger if e.date > client.as_of_date]
    return min([client.first_draft_date] + future)


def _additional_funds(client, rules, cadence, span, offer_total, program_fee, vectors) -> AdditionalFunds:
    hi         = _funds_upper_bound(client, rules, cadence, offer_total, program_fee)
    lump_date  = _earliest_credit_date(client)
    lump_cap   = round_half_up_pct(0.65, offer_total)

    def lump_feasible(amount: int) -> bool:
        return _is_feasible(
            _with_extra_credit(client, lump_date, amount),
            rules, cadence, span, program_fee, vectors,
        )

    lump_amt = _bisect_min(lump_feasible, hi)
    if lump_amt is None:
        lump = FundsOption(hi, False, "No schedule exists within the horizon for any lump sum.", date=lump_date)
    else:
        ok   = lump_amt <= lump_cap
        reason = "" if ok else f"Lump {lump_amt} exceeds guardrail {lump_cap} (round(0.65 x offer_total))."
        lump = FundsOption(lump_amt, ok, reason, date=lump_date)

    n       = _num_future_drafts(client)
    inc_cap = max(10000, round_half_up_pct(0.40, client.draft_amount_cents))
    if n == 0:
        inc = FundsOption(hi, False, "No future drafts to increase.", num_drafts=0)
    else:
        def inc_feasible(x: int) -> bool:
            return _is_feasible(
                _with_draft_increment(client, x),
                rules, cadence, span, program_fee, vectors,
            )

        inc_amt = _bisect_min(inc_feasible, hi)
        if inc_amt is None:
            inc = FundsOption(hi, False, "No schedule exists within the horizon for any draft increment.", num_drafts=n)
        else:
            ok     = inc_amt <= inc_cap
            reason = "" if ok else f"Increment {inc_amt} exceeds guardrail {inc_cap} (max(10000, round(0.40 x draft)))."
            inc    = FundsOption(inc_amt, ok, reason, num_drafts=n)

    return AdditionalFunds(lump_sum=lump, monthly_increment=inc)


def _diagnose(client, rules, cadence, span, program_fee, vectors, offer_total) -> dict:
    if not cadence:
        return {
            "kind": "no_cadence",
            "reason": "No cadence date falls on or before the horizon; the first "
                      "payment date is past last_draft_date, so nothing can be scheduled.",
            "binding_date": None,
            "shortfall_cents": None,
        }
    if not vectors:
        floors_min = sum(solver.floors_for_k(1, rules))
        return {
            "kind": "below_floor",
            "reason": f"offer_total ({offer_total}) cannot be met by any legal payment "
                      f"vector: even a single payment must be at least {floors_min} "
                      f"cents (the per-position floor), so no non-decreasing vector "
                      f"sums to the offer under the creditor's rules.",
            "binding_date": None,
            "shortfall_cents": None,
        }
    best = None
    for k, pays in vectors.items():
        sim = solver.simulate(client, rules, cadence, span, k, pays, program_fee, ScheduleRow)
        if sim.failure is None:
            continue
        kind, when, deficit = sim.failure
        key = (when, -deficit)
        if best is None or key > best[0]:
            best = (key, kind, when, deficit)
    if best is None:
        return {"kind": "unknown", "reason": "No feasible schedule.", "binding_date": None, "shortfall_cents": None}
    _, kind, when, deficit = best
    if kind == "balance_negative":
        reason = (
            f"With the cheapest feasible payment structure, the escrow balance "
            f"first goes negative on {when.isoformat()}, short by {deficit} cents. "
            f"Cash arriving after the last usable cadence date cannot help, so "
            f"extra funding must land on or before that date."
        )
    else:
        reason = (
            f"The creditor payments fit, but the program fee cannot be fully "
            f"collected by the horizon: {deficit} cents of fee remain "
            f"uncollected as of {when.isoformat()}."
        )
    return {"kind": kind, "reason": reason, "binding_date": when.isoformat(), "shortfall_cents": deficit}


def evaluate_offer(client: Client, offer: Offer, rules: CreditorRules, *, objective=DEFAULT_OBJECTIVE) -> Result:
    offer_total  = offer_total_cents(offer)
    program_fee  = program_fee_cents(offer, rules)
    cadence      = solver.cadence_dates(client, offer)
    span         = solver.term_limit(cadence, rules)
    k_max        = solver.max_payment_count(cadence, rules)
    shape        = _shape_family(rules)
    vectors      = solver.build_all_vectors(shape, offer_total, k_max, rules)

    if cadence and vectors:
        rows, sim, k = _best_schedule(client, rules, cadence, span, program_fee, vectors, objective)
        if rows is not None:
            diagnostics = {
                "min_balance_cents": sim.min_balance,
                "selected_k": k,
                "note": "min_balance_cents is the tightest buffer across the schedule (slack).",
            }
            return Result(True, shape, rows, None, diagnostics)

    funds       = _additional_funds(client, rules, cadence, span, offer_total, program_fee, vectors)
    diagnostics = _diagnose(client, rules, cadence, span, program_fee, vectors, offer_total)
    return Result(False, None, None, funds, diagnostics)
