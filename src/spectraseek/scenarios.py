"""Controlled, synthetic survey stress scenarios (not measured RF data)."""
import numpy as np
import pandas as pd

from .dataset import COLUMNS, simulate, validate

SCENARIOS = ('stationary', 'interference', 'drift')


def simulate_scenario(seed=42, sessions=40, sites=12, targets=18, *, scenario='stationary'):
    if scenario not in SCENARIOS:
        raise ValueError('Unknown synthetic scenario')
    if scenario == 'stationary':
        return simulate(seed, sessions, sites, targets)
    if sessions < 4 or sites < 2 or targets < 2:
        raise ValueError('Need >=4 sessions and >=2 sites and targets')
    rng = np.random.default_rng(seed)
    xy = rng.uniform(0, 40, (sites, 2))
    ap = rng.uniform(0, 40, (targets, 2))
    distance = np.linalg.norm(xy[:, None] - ap[None, :], axis=2)
    strength = 2.8 - distance / 7 + rng.normal(0, .65, (sites, targets))
    # Separate random stream keeps the common stochastic survey draws
    # aligned between scenarios, enabling controlled comparisons.
    stress_rng = np.random.default_rng(np.random.SeedSequence([seed, 1]))
    site_bias = stress_rng.normal(0, 1.2, (sites, 1))
    target_bias = stress_rng.normal(0, .8, (1, targets))
    rows = []
    for k in range(sessions):
        logits = strength + rng.normal(0, .55, (sites, 1)) + rng.normal(0, .45, (1, targets))
        if scenario == 'interference':
            # Some observation sites experience temporary attenuation.
            busy = stress_rng.random((sites, 1)) < .25
            logits = logits - 1.8 * busy
        elif scenario == 'drift':
            # A persistent regime change after the chronological midpoint.
            if k >= sessions // 2:
                logits = logits + site_bias + target_bias
        probability = 1 / (1 + np.exp(-logits))
        outcomes = rng.random((sites, targets)) < probability
        for i in range(sites):
            for j in range(targets):
                rows.append((f'{k:05d}', f'S{i+1:02d}', f'AP{j+1:02d}',
                             *xy[i], int(outcomes[i, j]), 'synthetic'))
    return validate(pd.DataFrame(rows, columns=COLUMNS))
