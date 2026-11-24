import numpy as np
import pytest

from spectraseek.adaptive import study
from spectraseek.dataset import simulate
from spectraseek.temporal import forecast, history_features


def test_history_features_and_forecast():
    h = np.array([[[0, 1], [1, 0]], [[1, 1], [0, 0]], [[0, 1], [1, 0]]])
    assert history_features(h).shape == (4, 5)
    assert np.allclose(history_features(h)[:, 0], [.4, .8, .6, .2])
    predictions = forecast(h)
    assert set(predictions) == {'recent_frequency', 'temporal_logistic'}
    for p in predictions.values():
        assert p.shape == (2, 2)
        assert ((p >= 0) & (p <= 1)).all()
    with pytest.raises(ValueError):
        forecast(np.zeros((3, 2, 2)))


def test_temporal_fixed_plan_does_not_use_current_window_labels():
    data = simulate(sessions=12, sites=4, targets=5)
    original = study(data, [1, 2], windows=2, include_temporal=True)
    changed = data.copy()
    ix = changed.session.isin(original['windows'][-1]['test_sessions'])
    changed.loc[ix, 'detected'] = 1 - changed.loc[ix, 'detected']
    modified = study(changed, [1, 2], windows=2, include_temporal=True)
    def plans(report):
        return [(r['session'], r['budget'], r['model'], r['sites'])
                for r in report['per_session'] if r['policy'] == 'fixed']
    assert plans(original) == plans(modified)
    assert any(r['model'] == 'temporal_logistic' for r in original['summary'])
