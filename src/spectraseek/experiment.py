"""Evaluate prediction and site selection on chronological survey windows."""

from hashlib import sha256
from importlib.metadata import version
from platform import python_version
from time import perf_counter

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import __version__
from .dataset import FEATURES, features, validate
from .planning import coverage, greedy, oracle

MODEL_TYPES = {'logistic': LogisticRegression, 'random_forest': RandomForestClassifier}
MODEL_SETTINGS = {
    'logistic': {'max_iter': 1000},
    'random_forest': {'n_estimators': 100, 'min_samples_leaf': 5, 'random_state': 42, 'n_jobs': 1},
}
EMPIRICAL = 'empirical_greedy'
RECOMMENDATION_STRATEGIES = (*MODEL_TYPES, EMPIRICAL)
RANDOM_TRIALS = 30
BOOTSTRAP_SAMPLES = 2000
DECISION_THRESHOLD = 0.5


def _fit_models(train, train_features, names, *, numeric_features=('x', 'y')):
    if train.detected.nunique() != 2:
        raise ValueError('Training data must include detection and nondetection outcomes')
    models = {}
    for name in names:
        prep = ColumnTransformer([
            ('categorical', OneHotEncoder(handle_unknown='ignore'), ['site', 'target', 'pair']),
            ('numeric', StandardScaler(), list(numeric_features)),
        ])
        model = make_pipeline(prep, MODEL_TYPES[name](**MODEL_SETTINGS[name]))
        models[name] = model.fit(train_features, train.detected)
    return models


def train_models(train):
    return _fit_models(train, features(train), MODEL_TYPES)


def _metrics(labels, probability):
    predicted = probability >= DECISION_THRESHOLD
    return {
        'accuracy': accuracy_score(labels, predicted),
        'precision': precision_score(labels, predicted, zero_division=0),
        'recall': recall_score(labels, predicted, zero_division=0),
        'f1': f1_score(labels, predicted, zero_division=0),
        'roc_auc': roc_auc_score(labels, probability) if labels.nunique() == 2 else None,
        'brier': brier_score_loss(labels, probability),
        'confusion_matrix': confusion_matrix(labels, predicted, labels=[0, 1]).tolist(),
    }


def _session_windows(sessions, windows):
    split = 3 * len(sessions) // 4 if windows == 1 else len(sessions) // 2
    test_count = len(sessions) - split
    if not 1 <= windows <= test_count:
        raise ValueError(f'Use between 1 and {test_count} evaluation windows for this dataset')
    boundaries = [split + number * test_count // windows for number in range(windows + 1)]
    return [(sessions[:start], sessions[start:end]) for start, end in zip(boundaries, boundaries[1:])]


def _coverage_differences(results, seed):
    by_session = results.pivot(index='session', columns='strategy', values='coverage_pct')
    rng = np.random.default_rng(seed)
    comparisons = {}
    for name in MODEL_TYPES:
        differences = (by_session[name] - by_session[EMPIRICAL]).dropna().to_numpy()
        interval = None
        if len(differences) >= 2:
            estimates = [rng.choice(differences, size=len(differences)).mean() for _ in range(BOOTSTRAP_SAMPLES)]
            interval = np.quantile(estimates, [0.025, 0.975]).tolist()
        comparisons[name] = {
            'sessions': len(differences),
            'mean_delta_pp': float(differences.mean()) if len(differences) else None,
            'bootstrap_95_ci_pp': interval,
        }
    return comparisons


def evaluate(data: pd.DataFrame, budget: int = 3, seed: int = 42, *, windows: int = 1) -> dict:
    df = validate(data)
    sessions = sorted(df.session.unique())
    sites = sorted(df.site.unique())
    targets = sorted(df.target.unique())
    if not 1 <= budget <= len(sites):
        raise ValueError('Budget must be between 1 and number of sites')

    splits = _session_windows(sessions, windows)
    pair_index = pd.MultiIndex.from_product([sites, targets], names=['site', 'target'])
    pairs = df.drop_duplicates(['site', 'target']).set_index(['site', 'target']).reindex(pair_index)
    pair_features = features(pairs.reset_index())
    shape = (len(sites), len(targets))

    rng = np.random.default_rng(seed)
    records, windows_report, label_chunks = [], [], []
    probability_chunks = {name: [] for name in RECOMMENDATION_STRATEGIES}
    training_seconds = 0.0
    for window, (train_sessions, test_sessions) in enumerate(splits, start=1):
        train = df[df.session.isin(train_sessions)]
        test = df[df.session.isin(test_sessions)]
        start = perf_counter()
        try:
            models = train_models(train)
        except ValueError as exc:
            raise ValueError(f'Window {window}: {exc}') from exc
        training_seconds += perf_counter() - start

        history = train.groupby(['site', 'target']).detected
        union = history.max().reindex(pair_index).to_numpy()
        probabilities = {EMPIRICAL: history.mean().reindex(pair_index).to_numpy()}
        for name, model in models.items():
            probabilities[name] = model.predict_proba(pair_features)[:, 1]

        plans = {'historical_greedy': greedy(union.reshape(shape), budget)}
        for name, estimates in probabilities.items():
            plans[name] = greedy(estimates.reshape(shape), budget)
        recommendations = {name: [sites[i] for i in plan] for name, plan in plans.items()}
        windows_report.append({
            'train_sessions': train_sessions,
            'test_sessions': test_sessions,
            'recommendations': recommendations,
        })

        for session, group in test.groupby('session', sort=True):
            labels = group.set_index(['site', 'target']).detected.reindex(pair_index)
            label_chunks.append(labels.reset_index(drop=True))
            for name, estimates in probabilities.items():
                probability_chunks[name].append(estimates)
            actual = labels.to_numpy().reshape(shape)
            available = int(actual.any(axis=0).sum())
            outcomes = {name: coverage(actual, plan) for name, plan in plans.items()}
            outcomes['random'] = np.mean([
                coverage(actual, rng.choice(len(sites), budget, replace=False).tolist())
                for _ in range(RANDOM_TRIALS)
            ])
            best = oracle(actual, budget)
            if best is not None:
                outcomes['offline_oracle'] = best
            for name, found in outcomes.items():
                records.append({
                    'session': str(session),
                    'window': window,
                    'strategy': name,
                    'found': float(found),
                    'available': available,
                    'coverage_pct': float(100 * found / available) if available else None,
                })

    labels = pd.concat(label_chunks, ignore_index=True)
    results = pd.DataFrame(records)
    results['coverage_pct'] = results.coverage_pct.astype(float)
    summary = []
    for name, group in results.groupby('strategy'):
        mean_pct = group.coverage_pct.mean()
        summary.append({
            'strategy': name,
            'mean_found': float(group.found.mean()),
            'mean_coverage_pct': float(mean_pct) if pd.notna(mean_pct) else None,
        })

    return {
        'source': str(df.source.iloc[0]),
        'rows': len(df),
        'train_sessions': splits[0][0],
        'test_sessions': [session for _, batch in splits for session in batch],
        'sites': len(sites),
        'targets': len(targets),
        'budget': budget,
        'training_seconds': training_seconds,
        'models': {
            name: _metrics(labels, np.concatenate(probability_chunks[name]))
            for name in MODEL_TYPES
        },
        'classification_baseline': {EMPIRICAL: _metrics(labels, np.concatenate(probability_chunks[EMPIRICAL]))},
        'strategies': summary,
        'coverage_vs_empirical': _coverage_differences(results, seed),
        'recommendations': windows_report[-1]['recommendations'],
        'windows': windows_report,
        'per_session': records,
        'experiment': {
            'dataset_sha256': sha256(df.to_csv(index=False, lineterminator='\n').encode('utf-8')).hexdigest(),
            'seed': seed,
            'features': FEATURES.copy(),
            'estimator_overrides': {name: params.copy() for name, params in MODEL_SETTINGS.items()},
            'decision_threshold': DECISION_THRESHOLD,
            'random_trials_per_session': RANDOM_TRIALS,
            'bootstrap_samples': BOOTSTRAP_SAMPLES,
            'environment': {
                'python': python_version(),
                'spectraseek': __version__,
                **{name: version(name) for name in ('numpy', 'pandas', 'scikit-learn', 'scipy', 'joblib')},
            },
        },
    }


def recommend(data: pd.DataFrame, visited=(), found=(), strategy='random_forest') -> dict:
    """Recommend one remaining approved site using completed historical sessions only."""
    df = validate(data)
    sites = sorted(df.site.unique())
    targets = sorted(df.target.unique())
    visited, found = set(visited), set(found)
    if not visited <= set(sites) or not found <= set(targets):
        raise ValueError('Visited sites and found targets must belong to the survey inventory')
    if strategy not in RECOMMENDATION_STRATEGIES:
        raise ValueError('Unknown recommendation strategy')

    remaining_sites = [site for site in sites if site not in visited]
    remaining_targets = [target for target in targets if target not in found]
    if not remaining_sites or not remaining_targets:
        return {'site': None, 'expected_new_targets': 0.0, 'ranked_sites': []}

    if strategy == EMPIRICAL:
        scores = df.groupby(['site', 'target']).detected.mean().rename('prob').reset_index()
    else:
        pairs = df.drop_duplicates(['site', 'target'])
        model = _fit_models(df, features(df), [strategy])[strategy]
        scores = pairs.assign(prob=model.predict_proba(features(pairs))[:, 1])

    eligible = scores[scores.site.isin(remaining_sites) & scores.target.isin(remaining_targets)]
    ranking = eligible.groupby('site').prob.sum().reset_index().sort_values(
        ['prob', 'site'], ascending=[False, True],
    )
    ranked = [
        {'site': str(row.site), 'expected_new_targets': float(row.prob)}
        for row in ranking.itertuples()
    ]
    return {**ranked[0], 'ranked_sites': ranked, 'strategy': strategy, 'source': str(df.source.iloc[0])}
