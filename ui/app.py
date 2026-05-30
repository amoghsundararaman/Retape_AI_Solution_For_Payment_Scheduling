"""FastAPI backend for the Settlement Feasibility & Fee Engine UI.

Serves the single-page frontend and exposes an evaluate endpoint that
accepts the three input JSON objects, runs the engine, and returns the
standard result plus a computed analytics block.

    uvicorn ui.app:app --reload --port 8000
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from feasibility.engine import evaluate_offer
from feasibility.models import (
    client_from_dict,
    offer_from_dict,
    rules_from_dict,
    offer_total_cents,
    program_fee_cents,
)
from feasibility.validation import validate_inputs, ValidationError

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Retape AI — Settlement Feasibility Engine",
    description=(
        "Given a client escrow account, a creditor settlement offer, and the "
        "creditor's rules, decides if the offer is affordable and — if so — "
        "produces the front-loaded fee schedule; otherwise computes the minimum "
        "additional funding required."
    ),
    version="1.0.0",
)

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"
STATIC_DIR = Path(__file__).resolve().parent / "static"


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class EvaluateRequest(BaseModel):
    client: dict[str, Any]
    offer: dict[str, Any]
    rules: dict[str, Any]


# ---------------------------------------------------------------------------
# Financial analytics (computed outside the engine to preserve the engine's
# output contract defined by ASSIGNMENT.md and the expected.json goldens)
# ---------------------------------------------------------------------------

def _compute_analytics(client_d, offer_d, rules_d, result_dict: dict) -> dict:
    """Derive financial metrics from parsed inputs + the engine result.

    These are additive: they are returned in a separate ``analytics`` key
    of the API response and never touch the ``result`` dict emitted by the
    engine.
    """
    offer_total = offer_d.get("settlement_pct", 0) * offer_d.get(
        "creditor_balance_cents", offer_d.get("current_balance_cents", 0)
    )
    original_bal = offer_d.get("original_balance_cents", 0)
    prog_fee_pct = rules_d.get("program_fee_pct", 0)
    bank_fee = rules_d.get("bank_fee_cents", 0)

    schedule = result_dict.get("schedule") or []
    n_payments = sum(1 for r in schedule if r["creditor_payment_cents"] > 0)
    total_bank_fees = sum(r["bank_fee_cents"] for r in schedule)
    total_prog_fee = sum(r["program_fee_cents"] for r in schedule)
    fee_only_months = sum(
        1 for r in schedule
        if r["creditor_payment_cents"] == 0 and r["program_fee_cents"] > 0
    )

    # Round the offer total to cents (mirrors models.round_half_up_pct)
    from decimal import Decimal, ROUND_HALF_UP
    offer_total_cents_val = int(
        (Decimal(str(offer_d.get("settlement_pct", 0)))
         * Decimal(str(offer_d.get("creditor_balance_cents", offer_d.get("current_balance_cents", 0)))))
        .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )

    savings_cents = original_bal - offer_total_cents_val
    total_cost_cents = offer_total_cents_val + total_prog_fee + total_bank_fees
    savings_pct = round(savings_cents / original_bal * 100, 2) if original_bal else 0.0

    analytics: dict[str, Any] = {
        "offer_total_cents": offer_total_cents_val,
        "program_fee_total_cents": total_prog_fee,
        "total_bank_fees_cents": total_bank_fees,
        "total_program_cost_cents": total_cost_cents,
        "savings_vs_full_balance_cents": savings_cents,
        "savings_pct": savings_pct,
        "n_creditor_payments": n_payments,
        "fee_only_months": fee_only_months,
    }
    if schedule:
        analytics["first_payment_date"] = schedule[0]["date"]
        analytics["last_payment_date"] = max(
            r["date"] for r in schedule if r["creditor_payment_cents"] > 0
        )
        analytics["plan_duration_months"] = len(schedule)
    return analytics


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/cases", summary="List available demo cases")
def list_cases() -> list[str]:
    """Return the names of all bundled demo cases."""
    if not CASES_DIR.is_dir():
        return []
    return sorted(
        d.name for d in CASES_DIR.iterdir()
        if d.is_dir() and all((d / f).exists() for f in ("client.json", "offer.json", "creditor_rules.json"))
    )


@app.get("/api/cases/{case_name}", summary="Load a demo case's three input files")
def get_case(case_name: str) -> dict[str, Any]:
    """Return client, offer, and rules JSON for a named demo case."""
    safe = Path(case_name).name  # strip any path traversal
    case_dir = CASES_DIR / safe
    required = ("client.json", "offer.json", "creditor_rules.json")
    if not case_dir.is_dir() or not all((case_dir / f).exists() for f in required):
        raise HTTPException(status_code=404, detail=f"Case '{safe}' not found.")
    return {
        "client": json.loads((case_dir / "client.json").read_text()),
        "offer": json.loads((case_dir / "offer.json").read_text()),
        "rules": json.loads((case_dir / "creditor_rules.json").read_text()),
    }


@app.post("/api/evaluate", summary="Evaluate a settlement offer")
def evaluate(req: EvaluateRequest) -> dict[str, Any]:
    """Parse and validate the three inputs, run the engine, and return the
    standard result plus a computed analytics block.

    The ``result`` key mirrors exactly what ``run.py`` prints — it is the
    engine's canonical output and satisfies the ASSIGNMENT.md output contract.
    The ``analytics`` key is additional context computed in this API layer.
    """
    try:
        client = client_from_dict(req.client)
        offer = offer_from_dict(req.offer)
        rules = rules_from_dict(req.rules)
        validate_inputs(client, offer, rules)
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    result = evaluate_offer(client, offer, rules)
    result_dict = result.to_dict()
    analytics = _compute_analytics(req.client, req.offer, req.rules, result_dict)

    return {"result": result_dict, "analytics": analytics}


@app.post("/api/validate", summary="Validate inputs without evaluating")
def validate_only(req: EvaluateRequest) -> dict[str, Any]:
    """Return a validation report for the three inputs without running the engine."""
    errors: list[str] = []
    try:
        client = client_from_dict(req.client)
        offer = offer_from_dict(req.offer)
        rules = rules_from_dict(req.rules)
        validate_inputs(client, offer, rules)
    except (KeyError, TypeError) as exc:
        errors.append(f"Parse error: {exc}")
    except ValidationError as exc:
        errors.append(str(exc))
    return {"valid": len(errors) == 0, "errors": errors}


# ---------------------------------------------------------------------------
# Serve the SPA (must come last so API routes take precedence)
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


# Mount static assets after defining all API routes
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
