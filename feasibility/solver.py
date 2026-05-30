from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import combinations

from feasibility.models import (
    Client,
    CreditorRules,
    Offer,
    default_first_payment_date,
    monthly_payment_dates,
)


def cadence_dates(client: Client, offer: Offer) -> list[date]:
    start   = offer.first_payment_date or default_first_payment_date(client)
    horizon = client.last_draft_date
    out: list[date] = []
    i = 0
    while i < 600:
        d = monthly_payment_dates(start, i + 1)[-1]
        if d > horizon:
            break
        out.append(d)
        i += 1
    return out


def term_limit(cadence: list[date], rules: CreditorRules) -> int:
    # max_terms caps total plan span; max_payments caps creditor-payment count.
    # Both are currently equal in the provided cases, but they compose differently
    # when fee-only months push the plan past the last creditor payment date.
    return min(len(cadence), rules.max_terms)


def max_payment_count(cadence: list[date], rules: CreditorRules) -> int:
    return min(rules.max_payments, term_limit(cadence, rules))


def floors_for_k(k: int, rules: CreditorRules) -> list[int]:
    """Per-position floor for k payments.

    Floor at position i = max of:
      - base min_payment_cents
      - base+1 when position exceeds max_token_pays (token-pay budget exhausted)
      - strictest active tier at position i

    'At most N payments at the base' is equivalent to 'every position past N exceeds
    the base' because payments are non-decreasing — enforcing one enforces the other.
    """
    base   = rules.min_payment_cents
    floors: list[int] = []
    for i in range(1, k + 1):
        f = base
        if i > rules.max_token_pays:
            f = max(f, base + 1)
        for frm, min_cents in rules.min_payment_tiers:
            if i >= frm:
                f = max(f, min_cents)
        floors.append(f)
    for i in range(1, len(floors)):
        floors[i] = max(floors[i], floors[i - 1])
    return floors


def is_valid_vector(
    pays: list[int],
    floors: list[int],
    offer_total: int,
    rules: CreditorRules,
    *,
    enforce_segments: bool,
    max_segments: int | None = None,
) -> bool:
    if len(pays) != len(floors) or not pays:
        return False
    if sum(pays) != offer_total:
        return False
    if any(p < f for p, f in zip(pays, floors)):
        return False
    if any(pays[i] < pays[i - 1] for i in range(1, len(pays))):
        return False
    if sum(1 for p in pays if p == rules.min_payment_cents) > rules.max_token_pays:
        return False
    if enforce_segments:
        assert max_segments is not None
        if len(set(pays)) > max_segments:
            return False
    return True


def build_even(k: int, offer_total: int, floors: list[int], rules: CreditorRules) -> list[int] | None:
    if k <= 0:
        return None
    q, r = divmod(offer_total, k)
    # Remainder on the latest payments keeps the sequence non-decreasing.
    pays = [q] * (k - r) + [q + 1] * r
    if is_valid_vector(pays, floors, offer_total, rules, enforce_segments=False):
        return pays
    return None


def build_balloon(k: int, offer_total: int, floors: list[int], rules: CreditorRules) -> list[int] | None:
    if k <= 0:
        return None
    early = list(floors[: k - 1])
    last  = offer_total - sum(early)
    pays  = early + [last]
    if is_valid_vector(pays, floors, offer_total, rules, enforce_segments=False):
        return pays
    return None


def _compositions(k: int, m: int):
    """All ordered ways to split k into m positive parts (contiguous block sizes)."""
    for cuts in combinations(range(1, k), m - 1):
        prev  = 0
        sizes = []
        for c in cuts:
            sizes.append(c - prev)
            prev = c
        sizes.append(k - prev)
        yield sizes


def build_staircase(
    k: int, offer_total: int, floors: list[int], rules: CreditorRules
) -> list[int] | None:
    """Lex-min non-decreasing vector with at most max_segments distinct levels.

    Searches over contiguous block layouts: early blocks sit at their floor,
    the final block absorbs the residual. Layouts where residual % block_size != 0
    are skipped; a single-payment final block always divides, so a valid layout
    exists whenever offer_total >= sum(floors).

    Complexity: O(k^(S-1)) for segment cap S — tiny for realistic inputs.
    """
    if k <= 0:
        return None
    s    = max(1, rules.max_segments)
    best: list[int] | None = None
    for m in range(1, min(s, k) + 1):
        for sizes in _compositions(k, m):
            block_floor: list[int] = []
            idx = 0
            for size in sizes:
                block_floor.append(max(floors[idx : idx + size]))
                idx += size
            vals: list[int] = []
            prev = 0
            for j in range(m - 1):
                v = max(prev, block_floor[j])
                vals.append(v)
                prev = v
            residual  = offer_total - sum(sizes[j] * vals[j] for j in range(m - 1))
            last_size = sizes[m - 1]
            if residual % last_size != 0:
                continue
            v_last = residual // last_size
            if v_last < max(prev, block_floor[m - 1]):
                continue
            vals.append(v_last)
            pays: list[int] = []
            for size, v in zip(sizes, vals):
                pays.extend([v] * size)
            if not is_valid_vector(
                pays, floors, offer_total, rules, enforce_segments=True, max_segments=s
            ):
                continue
            if best is None or pays < best:
                best = pays
    return best


def build_vector(shape: str, k: int, offer_total: int, rules: CreditorRules) -> list[int] | None:
    floors = floors_for_k(k, rules)
    if shape == "even":
        return build_even(k, offer_total, floors, rules)
    if shape == "balloon":
        return build_balloon(k, offer_total, floors, rules)
    return build_staircase(k, offer_total, floors, rules)


def build_all_vectors(shape: str, offer_total: int, k_max: int, rules: CreditorRules) -> dict[int, list[int]]:
    # Vectors depend only on (shape, offer_total, k, rules) — never on the ledger.
    # Build once and share between Part 1 selection and all Part 2 probes.
    out: dict[int, list[int]] = {}
    for k in range(1, k_max + 1):
        v = build_vector(shape, k, offer_total, rules)
        if v is not None:
            out[k] = v
    return out


@dataclass
class SimResult:
    feasible:    bool
    rows:        list
    fee_key:     tuple
    total_bank:  int
    min_balance: int
    failure:     tuple | None


def _ledger_flows(client: Client, horizon: date) -> tuple[dict, dict]:
    # Entries on or before as_of_date are baked into current_balance_cents — skip them.
    # Entries after the horizon are outside the planning window.
    credit_on: dict[date, int] = {}
    debit_on:  dict[date, int] = {}
    for e in client.ledger:
        if e.date <= client.as_of_date or e.date > horizon:
            continue
        bucket = credit_on if e.type == "credit" else debit_on
        bucket[e.date] = bucket.get(e.date, 0) + e.amount_cents
    return credit_on, debit_on


def simulate(
    client: Client,
    rules: CreditorRules,
    cadence: list[date],
    span: int,
    k: int,
    payments: list[int],
    program_fee: int,
    row_factory,
) -> SimResult:
    """Walk the timeline, greedily front-loading the program fee.

    Greedy-earliest fee is both objective-optimal and feasibility-optimal:
    skimming only free cash cannot push an earlier date negative, and
    collecting more fee early only raises later balances. So if any fee
    placement is feasible for a given payment vector, the greedy one is.
    """
    horizon    = client.last_draft_date
    pay_dates  = set(cadence[:k])
    fee_dates  = set(cadence[:span])
    fee_index  = {d: i for i, d in enumerate(cadence[:span])}
    pay_of     = {cadence[i]: payments[i] for i in range(k)}

    credit_on, debit_on = _ledger_flows(client, horizon)
    all_dates = sorted(set(credit_on) | set(debit_on) | pay_dates | fee_dates)

    balance       = client.current_balance_cents
    remaining_fee = program_fee
    total_bank    = 0
    min_balance   = balance
    rows          = []
    cum_fee       = [0] * span
    running       = 0
    failure       = None

    for d in all_dates:
        balance += credit_on.get(d, 0)
        balance -= debit_on.get(d, 0)
        cp  = pay_of.get(d, 0)
        bf  = rules.bank_fee_cents if d in pay_dates else 0
        total_bank += bf
        balance -= cp + bf
        if balance < min_balance:
            min_balance = balance
        if balance < 0 and failure is None:
            failure = ("balance_negative", d, -balance)
        fee_here = 0
        if d in fee_dates and remaining_fee > 0 and balance > 0:
            fee_here       = min(balance, remaining_fee)
            balance       -= fee_here
            remaining_fee -= fee_here
        if d in fee_index:
            running         += fee_here
            cum_fee[fee_index[d]] = running
        if d in fee_dates and (cp > 0 or fee_here > 0 or bf > 0):
            rows.append(row_factory(d, cp, fee_here, bf, balance))

    if failure is None and remaining_fee > 0:
        last    = cadence[span - 1] if span > 0 else horizon
        failure = ("fee_not_collected", last, remaining_fee)

    feasible = failure is None
    return SimResult(
        feasible=feasible,
        rows=rows if feasible else [],
        fee_key=tuple(cum_fee),
        total_bank=total_bank,
        min_balance=min_balance,
        failure=failure,
    )
