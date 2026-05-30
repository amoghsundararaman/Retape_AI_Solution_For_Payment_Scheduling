from __future__ import annotations

from feasibility.models import Client, CreditorRules, Offer


class ValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_client(c: Client) -> None:
    _require(c.draft_amount_cents >= 0, "client.draft_amount_cents must be >= 0")
    _require(1 <= c.draft_day <= 31, "client.draft_day must be in 1..31")
    _require(c.first_draft_date <= c.last_draft_date,
             "client.first_draft_date must be <= last_draft_date")
    for i, e in enumerate(c.ledger):
        _require(e.type in ("credit", "debit"),
                 f"ledger[{i}].type must be 'credit' or 'debit', got {e.type!r}")
        _require(e.amount_cents >= 0, f"ledger[{i}].amount_cents must be >= 0")


def validate_offer(o: Offer) -> None:
    _require(bool(o.creditor), "offer.creditor must be a non-empty string")
    _require(o.current_balance_cents >= 0, "offer.creditor_balance_cents must be >= 0")
    _require(o.original_balance_cents >= 0, "offer.original_balance_cents must be >= 0")
    _require(0.0 <= o.settlement_pct <= 1.0, "offer.settlement_pct must be in [0, 1]")


def validate_rules(r: CreditorRules) -> None:
    _require(r.max_terms >= 1, "rules.max_terms must be >= 1")
    _require(r.max_payments >= 1, "rules.max_payments must be >= 1")
    _require(r.min_payment_cents >= 0, "rules.min_payment_cents must be >= 0")
    _require(r.max_token_pays >= 0, "rules.max_token_pays must be >= 0")
    _require(r.max_segments >= 1, "rules.max_segments must be >= 1")
    _require(r.bank_fee_cents >= 0, "rules.bank_fee_cents must be >= 0")
    _require(r.program_fee_pct >= 0.0, "rules.program_fee_pct must be >= 0")
    for j, tier in enumerate(r.min_payment_tiers):
        _require(len(tier) == 2, f"rules.min_payment_tiers[{j}] must be [from_payment, min_cents]")
        frm, min_cents = tier
        _require(frm >= 1, f"rules.min_payment_tiers[{j}] from_payment must be >= 1 (1-based)")
        _require(min_cents >= 0, f"rules.min_payment_tiers[{j}] min_cents must be >= 0")


def validate_inputs(client: Client, offer: Offer, rules: CreditorRules) -> None:
    validate_client(client)
    validate_offer(offer)
    validate_rules(rules)
