import json

import numpy as np
import pytest

from spectraseek.adaptive import replay, study
from spectraseek.dataset import simulate


def test_adaptive_uses_only_revealed_outcomes():
    p = [[.9, .8, .0], [.8, .7, .0], [.0, .0, .15]]
    a = [[1, 1, 0], [1, 1, 0], [0, 0, 1]]
    b = [[1, 1, 0], [0, 0, 0], [0, 0, 0]]
    assert replay(p, a, 2) == ([0, 2], [2, 3])
    assert replay(p, b, 2)[0] == [0, 2]
    assert replay(p, a, 2, adaptive=False) == ([0, 1], [2, 2])


def test_replay_validates_and_never_revisits():
    p = np.ones((3, 2))
    trace, counts = replay(p, p, 3)
    assert trace == [0, 1, 2]
    assert counts == [2, 2, 2]
    with pytest.raises(ValueError):
        replay(p, [[2, 0]], 2)


def test_study_chronology_and_budget():
    data = simulate(sessions=12, sites=4, targets=5)
    report = study(data, [1, 2, 4], windows=2)
    assert len(report['summary']) == 9
    for window in report['windows']:
        assert max(window['train_sessions']) < min(window['test_sessions'])
    for row in report['per_session']:
        assert len(set(row['sites'])) == row['budget']
        assert row['found'] <= row['oracle_found'] <= row['available']
        if row['budget'] == 4:
            assert row['found'] == row['available']
    assert all(r['adaptive_delta_pp'] == 0 for r in report['summary'] if r['budget'] == 1)
    json.dumps(report, allow_nan=False)
    with pytest.raises(ValueError):
        study(data, [5])

def test_study_cli(tmp_path):
    from spectraseek.cli import main
    path = tmp_path / 'input.csv'
    out = tmp_path / 'study.json'
    simulate(sessions=8, sites=3, targets=4).to_csv(path, index=False)
    assert main(['study', str(path), '--budgets', '1', '3', '--output', str(out)]) == 0
    result = json.loads(out.read_text())
    assert result['budgets'] == [1, 3]
    assert result['source'] == 'synthetic'
