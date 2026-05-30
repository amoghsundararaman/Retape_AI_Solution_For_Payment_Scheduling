"""Ranking policy for feasible schedules.

An objective is (sim, k) -> key where larger key wins (Python tuple ordering).
Keeping this separate from the solver means swapping the economic policy is a
one-line change to evaluate_offer.
"""

from __future__ import annotations


def front_load_fee(sim, k: int):
    """Collect program fee as early as possible; tie-break toward fewer payments."""
    return (sim.fee_key, -k)


def min_bank_fees(sim, k: int):
    return (-sim.total_bank, sim.fee_key, -k)


def max_slack(sim, k: int):
    return (sim.min_balance, sim.fee_key, -k)


REGISTRY = {
    "front_load_fee": front_load_fee,
    "min_bank_fees":  min_bank_fees,
    "max_slack":      max_slack,
}

DEFAULT = front_load_fee
