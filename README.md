# Settlement Feasibility & Fee Engine

This is my solution to Retape AI's take-home. The assignment is deceptively compact — under a page of spec — but getting it fully right turned out to involve more edge cases than I expected, particularly around the date math, half-up rounding, and the interaction between the token-pay rule and the staircase shape. I've written this up the way I'd explain it to someone joining the codebase.

---

## Quick start

```bash
# clone and set up
pip install -r requirements.txt

# run a single case (the CLI)
python run.py cases/case1_feasible_even

# run all tests
pytest -q

# regression check: diff all four cases against their expected.json golden
python -m pipeline.batch cases --check

# launch the interactive UI
streamlit run ui/streamlit_app.py

# launch the REST API (Swagger docs at /docs)
uvicorn ui.app:app --reload --port 8000
```

The engine itself only needs the standard library. `pytest`, `streamlit`, `plotly`, `pandas`, `reportlab`, `fastapi`, and `uvicorn` are the extras.

---

## The problem

A client saves a fixed monthly amount into one escrow account. Out of that same account we pay off one debt to a creditor in monthly installments, take our own program fee, and pay the bank a small per-payment fee. The question is: does the money last? And if not, how much more do we need?

The output has two parts:

1. **Feasible** — produce a schedule that keeps the balance non-negative at every date, collects our fee as early as possible.
2. **Infeasible** — compute the minimum extra funding two independent ways: one lump sum and a uniform per-draft increment.

---

## How I think about it

The whole thing is a single bank account walked forward in time. Every input maps to a dated event on that account: the client's monthly drafts are credits (already in the ledger), previously committed debits are fixed, and on each "cadence" date the engine places a creditor payment, a bank fee, and some amount of program fee. Feasibility is just the question of whether there's a way to choose those placements so the balance never goes below zero.

The key structural insight, and the thing I want to flag because it's worth understanding: **the two decision layers — what to pay the creditor, and when to collect our fee — don't need to iterate against each other.** The fee total is fixed and must be fully collected by the horizon no matter what. So:

- Skimming fee only from free cash can't push an *earlier* date negative.
- Collecting fee early leaves less for later, so every later balance only gets higher — it can't push a *later* date negative either.

Greedy-earliest fee placement is simultaneously the most front-loaded and the most forgiving option. If any fee schedule is feasible for a given set of creditor payments, the greedy one is. That means I choose the payment vector first, then assign the fee, with no backtracking. This is the reason the two layers are independent, not just separate.

---

## Architecture

```
feasibility/
  models.py       data types, JSON loaders, date helpers, half-up rounding
  validation.py   semantic input checks before the solver sees anything
  solver.py       cadence dates, per-position floors, shape builders, simulation
  objectives.py   the ranking policy (front-load fee by default)
  engine.py       evaluate_offer: orchestration, Part 2 binary search, diagnostics
pipeline/
  batch.py        batch runner + golden regression gate
ui/
  streamlit_app.py  interactive UI with Plotly charts and PDF export
  app.py            FastAPI REST backend with OpenAPI documentation
cases/            four provided cases with expected.json goldens
tests/            76 tests
run.py            single-case CLI
```

The engine layers deliberately don't know about each other. `solver.py` handles mechanics; `engine.py` orchestrates; `objectives.py` holds the ranking policy as a pluggable function. Swapping the objective changes which schedule gets chosen without touching the solver. The UI and API layers are on top of all of this and add analytics and presentation without touching the engine's output contract.

---

## The payment shapes

The assignment deliberately leaves the shape open-ended. My interpretation:

**`even_pays = true` → even.** Every payment equal; if the total doesn't divide evenly by `k`, the leftover cents go on the latest payments (keeping it non-decreasing). `even_pays` wins outright even if ballooning is also set — the spec says ballooning is irrelevant when payments are forced equal, and that's the right reading.

**`is_ballooning_allowed = true` → balloon.** Early payments sit at their per-position floors (as small as the rules allow) and the final payment absorbs everything that's left. Maximum deferral of the creditor obligation means the most free cash early, which serves the fee front-loading objective directly.

**Otherwise → staircase.** A non-decreasing step function capped at `max_segments` distinct levels. I want the lexicographically smallest valid vector — smallest early payments leave the most cash for the fee. The search is over contiguous block layouts: early blocks sit at their floor, the final block absorbs the exact residual. Layouts where the residual doesn't divide the final block size are skipped. Because a single-payment final block always divides, a valid layout always exists when the offer total is at least the sum of the floors.

A few specific calls I had to make:

**The token-pay rule as a floor lift.** "At most N payments may equal the base minimum" is equivalent to "every position past N must exceed the base." Because payments are non-decreasing, those two statements are identical. I enforce it by lifting the floor to `base + 1` for positions past the token budget. This is provably equivalent, not an approximation.

**A big staircase terminal step is not a balloon.** When `is_ballooning_allowed` is false, I don't label anything "balloon." But a staircase is still allowed to put its largest level last — even as a single payment — as long as it's within the `max_segments` distinct-level budget. I read the balloon flag as governing the dedicated balloon shape and its label, not as a ban on a large terminal step the level budget already permits.

**Tiers and floors via max.** Tiers given out of order or overlapping just resolve to the strictest one at each position, because I take the max over all active tiers. Malformed tier inputs are harmless.

**`max_terms` vs `max_payments`.** The spec notes these are currently redundant and invites distinct meanings. I gave them some: `max_payments` caps the count of creditor payments; `max_terms` caps the total months the plan may span (creditor payments plus any trailing fee-only months). When they're equal (as in all four provided cases) nothing changes. `test_terms.py` shows the distinction biting when they differ.

**Choosing `k`, the tie-break.** Among feasible candidates I rank by cumulative fee collected at each cadence date, left to right (more fee, sooner, wins). Ties go to fewer payments — fewer bank fees, simpler plan. This is why case4 lands on `k = 10` rather than `k = 12`: the first six payments are identical either way so the fee front-loads identically, and ten payments beats twelve on the tie-break.

---

## Part 2: minimum extra funding

Feasibility is monotone in money — adding a credit can only raise balances, never break a working plan. Both minima are therefore binary searches over the same feasibility check Part 1 uses. The search has a provably-sufficient upper bound (`offer_total + program_fee + all bank fees + all committed debits + 1`), so it always brackets the answer.

**Lump sum.** One extra credit, placed on the earliest funded date (earlier is weakly more useful, which minimises the amount). Binary-search the smallest amount.

**Monthly increment.** A uniform amount added to every future draft. Binary-search the smallest one. `num_drafts` counts all future drafts, including any that land too late to help — that's the spec's intent, and it's why the lump and increment legitimately disagree in case2 (the fifth draft lands after the last usable cadence date, so it adds cash the increment needs but the lump doesn't).

The guardrails — increment capped at `max(10000, 0.40 × draft)`, lump capped at `0.65 × offer_total` — are checked after the minimum is found. Each option carries a `within_guardrail` flag and a reason string.

---

## Two things the scaffolding got wrong

Both are mentioned explicitly in the spec, which is why I noticed them.

**Rounding.** The spec demands half-up rounding and warns explicitly against the Python default. Python's `round()` is half-to-even: `round(0.5) == 0`, `round(2.5) == 2`. I replaced every money calculation with `Decimal`-based `round_half_up`. The four provided cases don't hit a `.5` boundary so their numbers are unchanged, but any new case can now.

**The renamed balance field.** The spec says the offer's balance was renamed from `current_balance_cents` to `creditor_balance_cents`, but the shipped loader and all four case JSON files still use `current_balance_cents`. I made the loader accept either key and added a `creditor_balance_cents` alias on the `Offer` class so both names work correctly.

---

## The UI platform

After getting the engine correct I added a Streamlit interface so the results are actually usable without reading JSON from the terminal.

```bash
streamlit run ui/streamlit_app.py
```

The sidebar has JSON editors for all three input files, pre-filled from any of the four demo cases. Submitting runs the engine and renders:

- Feasibility status banner with shape and payment count
- Six financial metrics: offer total, program fee, bank fees, total cost, savings vs full balance, minimum balance slack
- A payment timeline flow diagram
- A Plotly line chart of the running balance (zero-balance dates highlighted in amber)
- A stacked bar showing the creditor payment / program fee / bank fee split per date
- The full schedule as a sortable DataFrame
- When infeasible: the lump sum and monthly increment with guardrail pass/fail badges, and the binding cause diagnosis
- A download button that generates a PDF via `reportlab`

The financial analytics (savings percentage, total program cost, etc.) are computed in the UI layer, not in the engine. I kept them out of the engine's output to preserve the `expected.json` contract — the four golden files define the exact engine output format, and nothing in this project changes that.

---

## REST API

```bash
uvicorn ui.app:app --reload --port 8000
```

FastAPI with auto-generated Swagger docs at `http://localhost:8000/docs`. Endpoints:

- `POST /api/evaluate` — validates inputs, runs the engine, returns the standard result plus an analytics block
- `POST /api/validate` — validates inputs only, returns a list of errors without running the engine
- `GET /api/cases` — lists the demo cases
- `GET /api/cases/{name}` — returns the three JSON files for a named case

The `result` key in the response is exactly what `run.py` prints. The `analytics` key is the additional financial context computed in the API layer.

---

## The eval harness

`pipeline/batch.py` treats the engine like a model under test. It walks the cases directory, validates and runs each, and emits one JSONL record per case with the verdict and wall-clock timing. With `--check` it diffs each output against the committed `expected.json` golden and fails on any drift. Changing a single cent anywhere makes the gate go red. This is the right pattern for a deterministic engine: the golden files are the contract, and any refactor that accidentally changes behavior surfaces immediately.

---

## Tests

76 tests across `pytest`. The centrepiece is `assert_valid_schedule` in `tests/_helpers.py`: an independent validator that re-derives the running balance from scratch using only the engine's output rows and the original input ledger, then re-checks every hard constraint. It doesn't trust the engine's own bookkeeping. Most shape and feasibility tests funnel through it, so a regression anywhere shows up as a concrete constraint failure rather than a silent wrong number.

Beyond that: `test_shapes` for remainder placement, token rejection, staircase lex-min, segment cap, tier-forced steps, and balloon; `test_simulation` for same-day ordering, exact-zero balance, horizon edges, fee-only months, EOM and mid-month cadence; `test_part2` for both minima and their guardrails; `test_edge_cases` for summed same-date debits, a debit before the first credit, `as_of_date` boundary, `max_token_pays = 0`, overlapping tiers, and post-horizon debits; plus `test_diagnostics`, `test_objectives`, `test_validation`, `test_terms`, and `test_pipeline`.

---

## Assumptions and known limits

- All future ledger credits are treated as drafts for the purposes of the monthly increment. The spec's glossary says drafts are the credits, so this follows directly.
- Committed debits after `last_draft_date` are outside the planning window and aren't simulated. The conservative alternative (require solvency past the horizon too) is a one-line change in `_ledger_flows`.
- The lump sum is reported on the earliest funded date. If the starting balance on `as_of_date` is sufficient and no credits land before the first cadence date, the lump lands on `first_draft_date`.
- The cadence generator caps at 600 iterations as a guard against a pathological horizon. Real plans are a handful of months.

---

## What I'd build next

The engine is the deterministic core, and that's exactly the right thing to keep deterministic — it can say, with a proof, whether a proposed plan holds. The places ML belongs are *around* it:

- **Creditor acceptance prediction.** A model estimating the probability a creditor accepts a given `settlement_pct`, trained on historical outcomes. The engine verifies affordability of whatever the model proposes.
- **Draft delinquency forecasting.** This engine assumes every future draft arrives. A model predicting missed deposits turns the single feasibility verdict into a risk distribution.
- **Rule-sheet parsing.** Creditor rules come in as messy documents. An LLM extracts them into the strict schema this engine consumes, with `validation.py` as the gate that rejects a bad parse.
- **The engine as a labeler.** Because it's fast and deterministic, it can label large batches of synthetic cases for training or benchmarking a learned approximator. The `pipeline/` harness is already shaped like the front of that data pipeline.
