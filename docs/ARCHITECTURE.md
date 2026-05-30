# Architecture

One escrow account is simulated forward in time. Three JSON inputs are loaded,
validated, and handed to `evaluate_offer`, which either returns the best feasible
schedule (Part 1) or the minimum additional funding plus a diagnosis (Part 2).

```mermaid
flowchart TD
    A["Three JSON inputs<br/>client · offer · rules"] --> B["models.py — load<br/>explicit round-half-up · field alias"]
    B --> V["validation.py<br/>semantic data contract"]
    V --> C["engine.evaluate_offer<br/>orchestrator · feasible?"]
    C -->|feasible| L1
    C -->|infeasible| R1

    subgraph P1["Part 1 — feasible"]
        direction TB
        L1["Build payment vector<br/>even · balloon · staircase (lex-min)"]
        L2["Simulate timeline<br/>greedy fee · balance ≥ 0"]
        L3["Select best k<br/>objective: front-load fee"]
        L1 --> L2 --> L3
    end

    subgraph P2["Part 2 — infeasible"]
        direction TB
        R1["Binary-search funds<br/>min lump L · min increment X"]
        R2["Apply guardrails<br/>0.65×offer · max(10000, 0.40×draft)"]
        R3["Diagnose binding cause<br/>binding date · shortfall_cents"]
        R1 --> R2 --> R3
    end

    L3 --> RES["Result.to_dict()<br/>feasible · pay_shape_used · schedule · additional_funds · diagnostics"]
    R3 --> RES
```

## How the boxes map to the code

| Box | File / function |
| --- | --- |
| Load + round | `feasibility/models.py` — loaders, `round_half_up`, date helpers |
| Data contract | `feasibility/validation.py` — `validate_inputs` |
| Orchestrator | `feasibility/engine.py` — `evaluate_offer` |
| Build payment vector | `feasibility/solver.py` — `floors_for_k`, `build_even` / `build_balloon` / `build_staircase`, `build_all_vectors` |
| Simulate timeline | `feasibility/solver.py` — `simulate`, `_ledger_flows` |
| Select best k | `feasibility/engine.py` — `_best_schedule`; `feasibility/objectives.py` — the ranking policy |
| Binary-search funds | `feasibility/engine.py` — `_additional_funds`, `_bisect_min` |
| Guardrails | `feasibility/engine.py` — `_additional_funds` (lump and increment caps) |
| Diagnose | `feasibility/engine.py` — `_diagnose` |

## The eval harness around it

`pipeline/batch.py` wraps `evaluate_offer` to treat the engine like a model under
test: it walks a directory of cases, validates and runs each, and emits one JSONL
record per case with the verdict and wall-clock timing. With `--check` it diffs each
output against a committed `expected.json` golden and fails on any drift — the
deterministic-eval / regression pattern.

```mermaid
flowchart LR
    CASES["cases/*/<br/>client · offer · rules · expected.json"] --> BATCH["pipeline.batch<br/>discover · validate · evaluate"]
    BATCH -->|--out| JSONL["results.jsonl<br/>one record per case"]
    BATCH -->|--check| GATE["regression gate<br/>diff vs expected.json"]
```
