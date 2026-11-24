"""Offline replay of authorized survey policies; never performs live scans."""
from hashlib import sha256

import numpy as np

from .dataset import features, validate
from .experiment import EMPIRICAL, _session_windows, train_models
from .planning import greedy, oracle


def replay(probabilities, outcomes, budget, *, adaptive=True):
    """Return an ordered site trace and cumulative unique detections.

    Select before revealing a site's outcomes. The fixed control uses the
    same probabilities and budget, but never changes its initial plan.
    """
    p = np.asarray(probabilities, dtype=float)
    fixed = greedy(p, budget)
    actual = np.asarray(outcomes)
    if actual.shape != p.shape or not np.isin(actual, [0, 1]).all():
        raise ValueError('Outcomes must be a matching binary matrix')
    found = np.zeros(p.shape[1], dtype=bool)
    visited, cumulative = [], []
    for step in range(budget):
        if adaptive:
            gains = p @ (~found).astype(float)
            gains[visited] = -np.inf
            site = int(np.argmax(gains))
        else:
            site = fixed[step]
        visited.append(site)
        found |= actual[site].astype(bool)
        cumulative.append(int(found.sum()))
    return visited, cumulative


def study(data, budgets=(1, 2, 3), *, windows=1):
    """Train once per window; compare fixed and adaptive plans at each budget."""
    df = validate(data)
    sites = sorted(df.site.unique())
    targets = sorted(df.target.unique())
    sessions = sorted(df.session.unique())
    budgets = sorted(set(budgets))
    if not budgets or any(not isinstance(b, int) or not 1 <= b <= len(sites) for b in budgets):
        raise ValueError('Budgets must be integers between 1 and the site count')
    records = []
    splits = _session_windows(sessions, windows)
    for number, (train_ids, test_ids) in enumerate(splits, 1):
        train = df[df.session.isin(train_ids)]
        pairs = train.drop_duplicates(['site', 'target']).sort_values(['site', 'target'])
        shape = (len(sites), len(targets))
        probabilities = {
            EMPIRICAL: train.groupby(['site', 'target'], sort=True).detected.mean().to_numpy().reshape(shape),
        }
        for name, model in train_models(train).items():
            probabilities[name] = model.predict_proba(features(pairs))[:, 1].reshape(shape)
        test = df[df.session.isin(test_ids)]
        for session, group in test.groupby('session', sort=True):
            actual = group.sort_values(['site', 'target']).detected.to_numpy().reshape(shape)
            available = int(actual.any(axis=0).sum())
            for budget in budgets:
                upper = oracle(actual, budget)
                for name, p in probabilities.items():
                    for adaptive in (False, True):
                        trace, cumulative = replay(p, actual, budget, adaptive=adaptive)
                        records.append({
                            'window': number, 'session': str(session), 'budget': budget,
                            'model': name, 'policy': 'adaptive' if adaptive else 'fixed',
                            'sites': [sites[i] for i in trace], 'cumulative_found': cumulative,
                            'found': cumulative[-1], 'available': available,
                            'coverage_pct': 100 * cumulative[-1] / available if available else None,
                            'oracle_found': upper,
                        })
    summary = []
    for budget in budgets:
        for name in probabilities:
            group = [r for r in records if r['budget'] == budget and r['model'] == name]
            fixed = [r for r in group if r['policy'] == 'fixed']
            adaptive = [r for r in group if r['policy'] == 'adaptive']
            deltas = [a['coverage_pct'] - f['coverage_pct'] for a, f in zip(adaptive, fixed)
                      if a['coverage_pct'] is not None]
            summary.append({
                'budget': budget, 'model': name, 'sessions': len(fixed),
                'coverage_sessions': len(deltas),
                'fixed_mean_found': float(np.mean([r['found'] for r in fixed])),
                'adaptive_mean_found': float(np.mean([r['found'] for r in adaptive])),
                'adaptive_delta_pp': float(np.mean(deltas)) if deltas else None,
            })
    return {
        'source': str(df.source.iloc[0]),
        'dataset_sha256': sha256(df.to_csv(index=False, lineterminator='\n').encode()).hexdigest(),
        'windows': [{'train_sessions': a, 'test_sessions': b} for a, b in splits],
        'budgets': budgets, 'summary': summary, 'per_session': records,
    }
