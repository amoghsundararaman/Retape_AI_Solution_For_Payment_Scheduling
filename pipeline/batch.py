"""Batch runner: treat the engine like a model under test.

Walks a directory of case folders (each with client.json / offer.json /
creditor_rules.json), validates and evaluates each, and emits one structured
JSONL record per case with the verdict and wall-clock timing. With ``--check``
it compares each engine output against the committed ``expected.json`` golden
and fails loudly on any drift — the deterministic-eval / regression pattern.

    python -m pipeline.batch cases --out results.jsonl
    python -m pipeline.batch cases --check
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from feasibility.engine import evaluate_offer
from feasibility.models import load_case
from feasibility.validation import validate_inputs

CASE_FILES = ("client.json", "offer.json", "creditor_rules.json")


def discover_cases(root: Path) -> list[Path]:
    """Every immediate subdirectory of ``root`` that holds the three inputs."""
    return sorted(
        d for d in root.iterdir()
        if d.is_dir() and all((d / f).exists() for f in CASE_FILES)
    )


def evaluate_case(case_dir: Path) -> dict:
    """Run one case, returning a flat record plus the full serialized result."""
    client, offer, rules = load_case(case_dir)
    validate_inputs(client, offer, rules)
    start = time.perf_counter()
    result = evaluate_offer(client, offer, rules)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
    out = result.to_dict()
    af = out.get("additional_funds")
    record = {
        "case": case_dir.name,
        "feasible": out["feasible"],
        "pay_shape_used": out["pay_shape_used"],
        "num_payments": sum(1 for r in (out["schedule"] or []) if r["creditor_payment_cents"] > 0),
        "lump_cents": af["lump_sum"]["amount_cents"] if af else None,
        "increment_cents": af["monthly_increment"]["amount_cents"] if af else None,
        "diagnostics_kind": (out.get("diagnostics") or {}).get("kind"),
        "elapsed_ms": elapsed_ms,
        "result": out,
    }
    return record


def run_batch(root: Path) -> list[dict]:
    return [evaluate_case(d) for d in discover_cases(root)]


def check_goldens(root: Path) -> int:
    """Compare each case's output to its expected.json. Returns failure count."""
    failures = 0
    for case_dir in discover_cases(root):
        golden_path = case_dir / "expected.json"
        actual = evaluate_case(case_dir)["result"]
        if not golden_path.exists():
            print(f"MISSING golden: {case_dir.name}/expected.json")
            failures += 1
            continue
        expected = json.loads(golden_path.read_text())
        if actual != expected:
            print(f"DRIFT in {case_dir.name}: output differs from expected.json")
            failures += 1
        else:
            print(f"ok  {case_dir.name}")
    return failures


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Batch-evaluate settlement cases.")
    p.add_argument("cases_dir", help="directory containing case subfolders")
    p.add_argument("--out", help="write JSONL records to this path")
    p.add_argument("--check", action="store_true", help="compare against expected.json goldens")
    args = p.parse_args(argv)

    root = Path(args.cases_dir)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    if args.check:
        failures = check_goldens(root)
        print(f"\n{'PASS' if failures == 0 else 'FAIL'}: {failures} drift(s)")
        return 1 if failures else 0

    records = run_batch(root)
    lines = [json.dumps({k: v for k, v in r.items() if k != "result"}) for r in records]
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {len(records)} records to {args.out}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
