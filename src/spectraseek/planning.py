"""Budgeted maximum coverage over approved survey sites and AP inventory."""
from itertools import combinations
from math import comb
import numpy as np


def greedy(probabilities: np.ndarray, budget: int) -> list[int]:
    """Maximize expected unique coverage under a conditional independence approximation."""
    p = np.asarray(probabilities, dtype=float)
    if p.ndim != 2 or not p.shape[1] or not 1 <= budget <= p.shape[0]:
        raise ValueError('Invalid matrix or budget')
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError('Probabilities must be within [0,1]')
    remaining = np.ones(p.shape[1]); selected = []
    for _ in range(budget):
        gain = p @ remaining
        gain[selected] = -np.inf
        i = int(np.argmax(gain))
        selected.append(i); remaining *= 1 - p[i]
    return selected


def coverage(outcomes: np.ndarray, selected: list[int]) -> int:
    return int(np.any(outcomes[selected], axis=0).sum()) if selected else 0


def oracle(outcomes: np.ndarray, budget: int, limit: int = 50_000) -> int | None:
    """Offline reference only: knows held-out outcomes, not a deployable strategy."""
    if comb(len(outcomes), budget) > limit:
        return None
    return max(coverage(outcomes, list(c)) for c in combinations(range(len(outcomes)), budget))
