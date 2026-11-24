"""Chronologically held-out sessions, predictive metrics and budgeted discovery comparison."""
from time import perf_counter
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, brier_score_loss, confusion_matrix
from .dataset import validate, features
from .planning import greedy, coverage, oracle


def train_models(train):
    if train.detected.nunique() != 2:
        raise ValueError('Training data must include detection and nondetection outcomes')
    models = {}
    for name, estimator in [('logistic', LogisticRegression(max_iter=1000)), ('random_forest', RandomForestClassifier(n_estimators=100, min_samples_leaf=5, random_state=42, n_jobs=1))]:
        prep = ColumnTransformer([('cat', OneHotEncoder(handle_unknown='ignore'), ['site', 'target', 'pair']), ('num', StandardScaler(), ['x','y'])])
        model = make_pipeline(prep, estimator)
        model.fit(features(train), train.detected)
        models[name] = model
    return models


def evaluate(data: pd.DataFrame, budget: int = 3, seed: int = 42) -> dict:
    df = validate(data)
    sessions = sorted(df.session.unique()); split = max(2, int(.75 * len(sessions)))
    train = df[df.session.isin(sessions[:split])]; test = df[df.session.isin(sessions[split:])]
    sites = sorted(df.site.unique()); targets = sorted(df.target.unique())
    if not 1 <= budget <= len(sites):
        raise ValueError('Budget must be between 1 and number of sites')
    start = perf_counter(); models = train_models(train); training_seconds = perf_counter() - start
    metrics = {}; predicted = {}
    for name, model in models.items():
        prob = model.predict_proba(features(test))[:, 1]; pred = prob >= .5; y = test.detected
        metrics[name] = {'accuracy': accuracy_score(y, pred), 'precision': precision_score(y, pred, zero_division=0), 'recall': recall_score(y,pred,zero_division=0), 'f1': f1_score(y,pred,zero_division=0), 'roc_auc': roc_auc_score(y,prob) if y.nunique() == 2 else None, 'brier': brier_score_loss(y,prob), 'confusion_matrix': confusion_matrix(y,pred,labels=[0,1]).tolist()}
        predicted[name] = test.assign(prob=prob)
    # Historical baselines see training data only. Union ignores frequency; empirical estimates it.
    def matrix(frame, value, agg):
        return frame.pivot_table(index='site',columns='target',values=value,aggfunc=agg).reindex(index=sites,columns=targets).to_numpy()
    union = matrix(train,'detected','max'); empirical = matrix(train,'detected','mean')
    rng = np.random.default_rng(seed); records = []; recommendations = {}
    for session, group in test.groupby('session',sort=True):
        actual = matrix(group,'detected','max'); available = coverage(actual,list(range(len(sites))))
        plans = {'historical_greedy':greedy(union,budget), 'empirical_greedy':greedy(empirical,budget)}
        for name, frame in predicted.items():
            plans[name] = greedy(matrix(frame[frame.session == session],'prob','mean'),budget)
        outcomes = {name:coverage(actual, plan) for name,plan in plans.items()}
        outcomes['random'] = float(np.mean([coverage(actual,rng.choice(len(sites),budget,replace=False).tolist()) for _ in range(30)]))
        best = oracle(actual,budget)
        if best is not None: outcomes['offline_oracle'] = best
        for strategy, found in outcomes.items():
            records.append({'session':str(session),'strategy':strategy,'found':float(found),'available':available,'coverage_pct':100*found/available if available else None})
        recommendations = {name:[sites[i] for i in plan] for name,plan in plans.items()}
    results = pd.DataFrame(records); summary = []
    for name,group in results.groupby('strategy'):
        mean_pct = group.coverage_pct.mean()
        summary.append({'strategy':name,'mean_found':float(group.found.mean()),'mean_coverage_pct':float(mean_pct) if pd.notna(mean_pct) else None})
    return {'source':str(df.source.iloc[0]),'rows':len(df),'train_sessions':sessions[:split],'test_sessions':sessions[split:],'sites':len(sites),'targets':len(targets),'budget':budget,'training_seconds':training_seconds,'models':metrics,'strategies':summary,'recommendations':recommendations,'per_session':records}


def recommend(data: pd.DataFrame, visited=(), found=(), strategy='random_forest') -> dict:
    """Recommend one remaining approved site using completed historical sessions only."""
    df = validate(data)
    sites = sorted(df.site.unique()); targets = sorted(df.target.unique())
    visited, found = set(visited), set(found)
    if not visited <= set(sites) or not found <= set(targets):
        raise ValueError('Visited sites and found targets must belong to the survey inventory')
    remaining_sites = [s for s in sites if s not in visited]
    remaining_targets = [t for t in targets if t not in found]
    if not remaining_sites or not remaining_targets:
        return {'site': None, 'expected_new_targets': 0.0, 'ranked_sites': []}
    if strategy not in {'logistic','random_forest','empirical_greedy'}:
        raise ValueError('Unknown recommendation strategy')
    pairs = df.drop_duplicates(['site','target']).copy()
    if strategy == 'empirical_greedy':
        scores = df.groupby(['site','target']).detected.mean().rename('prob').reset_index()
    else:
        model = train_models(df)[strategy]
        scores = pairs.assign(prob=model.predict_proba(features(pairs))[:,1])
    ranking = scores[scores.site.isin(remaining_sites) & scores.target.isin(remaining_targets)].groupby('site').prob.sum().reset_index()
    ranking = ranking.sort_values(['prob','site'],ascending=[False,True])
    ranked = [{'site':str(row.site),'expected_new_targets':float(row.prob)} for row in ranking.itertuples()]
    return {**ranked[0], 'ranked_sites': ranked, 'strategy':strategy, 'source':str(df.source.iloc[0])}
