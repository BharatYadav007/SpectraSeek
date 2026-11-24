"""Experimental forecasting from prior complete survey sessions only."""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

RECENT_WINDOW = 5


def history_features(history):
    """One row per site/target, using strictly prior binary outcomes."""
    h = np.asarray(history, dtype=float)
    if h.ndim != 3 or min(h.shape) == 0 or not np.isin(h, [0, 1]).all():
        raise ValueError('Expected nonempty session/site/target binary history')
    _, sites, targets = h.shape
    recent = h[-RECENT_WINDOW:]
    long_rate = (h.sum(axis=0) + 1) / (len(h) + 2)
    short_rate = (recent.sum(axis=0) + 1) / (len(recent) + 2)
    site_rate = np.broadcast_to(h.mean(axis=(0, 2))[:, None], (sites, targets))
    target_rate = np.broadcast_to(h.mean(axis=(0, 1))[None, :], (sites, targets))
    return np.column_stack([x.ravel() for x in (long_rate, short_rate, h[-1], site_rate, target_rate)])


def forecast(history):
    """Fit lagged examples and forecast the next window without test outcomes."""
    h = np.asarray(history, dtype=float)
    final = history_features(h)
    predictions = {'recent_frequency': final[:, 1].reshape(h.shape[1:])}
    if len(h) < 2:
        raise ValueError('Temporal forecasting requires at least two prior sessions')
    x = np.concatenate([history_features(h[:i]) for i in range(1, len(h))])
    y = h[1:].reshape(-1)
    if len(np.unique(y)) < 2:
        raise ValueError('Temporal training examples must include both outcome classes')
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    model.fit(x, y)
    predictions['temporal_logistic'] = model.predict_proba(final)[:, 1].reshape(h.shape[1:])
    return predictions
