"""Exploratory held-out scoring for timestamp-aligned Wi-Fi pilot scans."""

import json

import numpy as np
import pandas as pd

from .experiment import MODEL_TYPES, _fit_models, _metrics
from .planning import coverage, greedy

MIN_TRAIN_ROUNDS = 8
MIN_TEST_ROUNDS = 4
MIN_CLASS_ROUNDS = 3


def evaluate_pairs(pairs, *, verified_rounds=False):
    """Use one fixed chronological holdout, with no outcomes from the test period in training."""
    split = 3 * len(pairs) // 4
    train, test = pairs[:split], pairs[split:]
    purged = 0
    if test:
        test_start = min(scan['timestamp'] for pair in test for scan in pair[:2])
        train = [pair for pair in train if max(scan['timestamp'] for scan in pair[:2]) < test_start]
        purged = split - len(train)

    train_data, test_data = map(_round_data, (train, test))
    report = {
        'status': 'unsupported',
        'train_rounds': len(train),
        'test_rounds': len(test),
        'purged_rounds': purged,
        'train_last_utc': max(scan['timestamp'] for pair in train for scan in pair[:2]).isoformat() if train else None,
        'test_first_utc': min(scan['timestamp'] for pair in test for scan in pair[:2]).isoformat() if test else None,
        'support': {'train': _support(train_data), 'test': _support(test_data)},
        'coverage': {
            'status': 'unsupported',
            'reason': 'Search coverage requires shared target identity and verified common collection rounds.',
        },
    }
    reasons = []
    for name, minimum in (('train', MIN_TRAIN_ROUNDS), ('test', MIN_TEST_ROUNDS)):
        count = report[f'{name}_rounds']
        support = report['support'][name]
        if count < minimum:
            reasons.append(f'{name} has {count} rounds; at least {minimum} are required')
        if min(support['positive_rounds'], support['negative_rounds']) < MIN_CLASS_ROUNDS:
            reasons.append(f'{name} needs both outcomes represented in at least {MIN_CLASS_ROUNDS} rounds each')
        if support['distinct_round_patterns'] < 2:
            reasons.append(f'{name} needs at least two distinct site/target detection patterns')
    if reasons:
        report['reason'] = '; '.join(reasons) + '.'
        if verified_rounds:
            report['coverage']['reason'] = 'Coverage requires a supported chronological holdout.'
        return report

    columns = ['site', 'target', 'pair']
    grid = train_data[columns].drop_duplicates().set_index('pair', drop=False)
    probabilities = {
        name: pd.Series(model.predict_proba(grid)[:, 1], index=grid.index)
        for name, model in _fit_models(train_data, train_data[columns], MODEL_TYPES,
                                       numeric_features=()).items()
    }
    probabilities['empirical_pair_frequency'] = train_data.groupby('pair').detected.mean()
    probabilities['empirical_global_frequency'] = pd.Series(train_data.detected.mean(), index=grid.index)
    report.update(
        status='exploratory',
        models={
            name: _metrics(test_data.detected, test_data.pair.map(estimates).to_numpy())
            for name, estimates in probabilities.items()
        },
    )
    if verified_rounds:
        report['coverage'] = _coverage(test_data, {
            name: estimates.reindex(grid.index).to_numpy() for name, estimates in probabilities.items()
        })
    return report


def _round_data(pairs):
    rows = [
        (index, scan['site'], target, json.dumps([scan['site'], target]), int(quality is not None))
        for index, pair in enumerate(pairs)
        for scan in sorted(pair[:2], key=lambda item: item['site'])
        for target, quality in sorted(scan['targets'].items())
    ]
    return pd.DataFrame(rows, columns=['round', 'site', 'target', 'pair', 'detected'])


def _support(data):
    counts = data.groupby('round').detected.agg(['min', 'max'])
    return {
        'positives': int(data.detected.sum()),
        'negatives': int(len(data) - data.detected.sum()),
        'positive_rounds': int(counts['max'].eq(1).sum()),
        'negative_rounds': int(counts['min'].eq(0).sum()),
        'distinct_round_patterns': data.pivot(index='round', columns='pair', values='detected')
        .drop_duplicates().shape[0],
    }


def _coverage(test, predictions):
    sites = sorted(test.site.unique())
    targets = test.target.nunique()
    actual = test.detected.to_numpy().reshape(-1, len(sites), targets)
    available = actual.any(axis=1).sum(axis=1)
    valid = available > 0
    if not valid.any():
        return {'status': 'unsupported', 'reason': 'No detectable targets in the held-out rounds.'}
    rows = []
    for name, probabilities in predictions.items():
        estimates = probabilities.reshape(len(sites), targets)
        for budget in range(1, len(sites) + 1):
            plan = greedy(estimates, budget)
            found = np.array([coverage(outcomes, plan) for outcomes in actual])
            rows.append({
                'model': name, 'budget': budget, 'sites': [sites[i] for i in plan],
                'mean_coverage_pct': float(100 * np.mean(found[valid] / available[valid])),
                'mean_targets_per_scan': float(np.mean(found) / budget),
                'coverage_rounds': int(valid.sum()), 'test_rounds': len(actual),
            })
    return {'status': 'exploratory', 'strategies': rows}
