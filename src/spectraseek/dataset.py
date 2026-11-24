"""A complete survey records a binary outcome for every registered target at each site."""
from __future__ import annotations
import numpy as np
import pandas as pd

COLUMNS = ['session', 'site', 'target', 'x', 'y', 'detected', 'source']
FEATURES = ['site', 'target', 'pair', 'x', 'y']


def validate(data: pd.DataFrame) -> pd.DataFrame:
    missing = set(COLUMNS) - set(data.columns)
    if missing:
        raise ValueError(f'Missing columns: {sorted(missing)}')
    df = data[COLUMNS].copy()
    if df.empty or df.isna().any().any():
        raise ValueError('Dataset must be nonempty and contain no missing values')
    for col in ['session', 'site', 'target', 'source']:
        df[col] = df[col].astype(str).str.strip()
        if (df[col] == '').any():
            raise ValueError(f'Empty {col}')
    if not set(df.source).issubset({'synthetic', 'measured'}) or df.source.nunique() != 1:
        raise ValueError('Use one data source type: synthetic or measured')
    for col in ['x', 'y', 'detected']:
        df[col] = pd.to_numeric(df[col], errors='raise')
        if not np.isfinite(df[col]).all():
            raise ValueError(f'Non-finite {col}')
    if not df.detected.isin([0, 1]).all():
        raise ValueError('detected must be 0 or 1')
    df.detected = df.detected.astype(int)
    if df.duplicated(['session', 'site', 'target']).any():
        raise ValueError('Duplicate session/site/target record')
    if (df.groupby('site')[['x', 'y']].nunique() > 1).any().any():
        raise ValueError('Site coordinates must be consistent')
    expected = df.site.nunique() * df.target.nunique()
    if not (df.groupby('session').size() == expected).all():
        raise ValueError('Each session must cover every site and target, including nondetections')
    if df.session.nunique() < 4:
        raise ValueError('At least four complete survey sessions are required')
    return df.sort_values(['session', 'site', 'target']).reset_index(drop=True)


def features(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(pair=[f'{len(s)}:{s}{t}' for s, t in zip(df.site, df.target)])[FEATURES]


def simulate(seed: int = 42, sessions: int = 40, sites: int = 12, targets: int = 18) -> pd.DataFrame:
    """Synthetic fixed-site survey; no real AP locations or live measurements."""
    if sessions < 4 or sites < 2 or targets < 2:
        raise ValueError('Need >=4 sessions and >=2 sites and targets')
    rng = np.random.default_rng(seed)
    xy = rng.uniform(0, 40, (sites, 2))
    ap = rng.uniform(0, 40, (targets, 2))
    distance = np.linalg.norm(xy[:, None] - ap[None, :], axis=2)
    strength = 2.8 - distance / 7 + rng.normal(0, .65, (sites, targets))
    rows = []
    for k in range(sessions):
        logits = strength + rng.normal(0, .55, (sites, 1)) + rng.normal(0, .45, (1, targets))
        probability = 1 / (1 + np.exp(-logits))
        outcomes = rng.random((sites, targets)) < probability
        for i in range(sites):
            for j in range(targets):
                rows.append((f'{k:05d}', f'S{i+1:02d}', f'AP{j+1:02d}', *xy[i], int(outcomes[i,j]), 'synthetic'))
    return validate(pd.DataFrame(rows, columns=COLUMNS))
