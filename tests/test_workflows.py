"""Regression coverage for CSV ingestion, the dashboard and evaluation windows."""

import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from spectraseek.cli import main
from spectraseek.dataset import simulate
from spectraseek.experiment import evaluate


def test_csv_cli_preserves_identifiers(tmp_path, capsys):
    data = simulate(sessions=8, sites=2, targets=2)
    data['site'] = data.site.map({'S01': '01', 'S02': '1'})
    data['target'] = data.target.map({'AP01': 'NA', 'AP02': 'NULL'})
    path = tmp_path / 'survey.csv'
    data.to_csv(path, index=False)

    output = tmp_path / 'evaluation.json'
    assert main(['evaluate', str(path), '--budget', '1', '--windows', '2', '--output', str(output)]) == 0
    result = json.loads(output.read_text(encoding='utf-8'))
    assert len(result['windows']) == 2
    assert result['train_sessions'][1] == '00001'
    assert result['sites'] == result['targets'] == 2

    capsys.readouterr()
    assert main(['recommend', str(path), '--visited', '01', '--found', 'NA', '--strategy', 'empirical_greedy']) == 0
    recommendation = json.loads(capsys.readouterr().out)
    assert recommendation['site'] == '1'
    assert 0 <= recommendation['expected_new_targets'] <= 1


def test_dashboard_single_site_upload_and_recommendation(monkeypatch):
    data = simulate(sessions=8, sites=2, targets=2)
    csv = data[data.site == 'S01'].to_csv(index=False).encode()
    monkeypatch.setattr(st.sidebar, 'file_uploader', lambda *args, **kwargs: io.BytesIO(csv))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'dashboard.py').run(timeout=30)

    assert not app.exception
    assert not app.error
    assert any(metric.label == 'Sites' and metric.value == '1' for metric in app.metric)

    app.multiselect[0].set_value(['S01'])
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert any(message.value == 'No remaining sites or targets.' for message in app.info)


def test_expanding_windows_use_only_prior_labels():
    data = simulate(sessions=12, sites=4, targets=5)
    result = evaluate(data, budget=2, windows=3)
    tested = []
    for window in result['windows']:
        assert window['train_sessions'] == result['train_sessions'] + tested
        assert max(window['train_sessions']) < min(window['test_sessions'])
        tested.extend(window['test_sessions'])
    assert tested == result['test_sessions'] == sorted(data.session.unique())[6:]
    assert np.sum(result['models']['logistic']['confusion_matrix']) == len(tested) * 4 * 5

    modified = data.copy()
    in_last_window = modified.session.isin(result['windows'][-1]['test_sessions'])
    modified.loc[in_last_window, 'detected'] = 1 - modified.loc[in_last_window, 'detected']
    assert evaluate(modified, budget=2, windows=3)['windows'] == result['windows']

    by_session = pd.DataFrame(result['per_session']).pivot(
        index='session', columns='strategy', values='coverage_pct',
    )
    expected_delta = (by_session.logistic - by_session.empirical_greedy).dropna()
    comparison = result['coverage_vs_empirical']['logistic']
    assert comparison['sessions'] == len(expected_delta)
    assert np.isclose(comparison['mean_delta_pp'], expected_delta.mean())
    assert comparison['bootstrap_95_ci_pp'] is not None


def test_evaluation_with_no_detectable_heldout_targets():
    data = simulate(sessions=8, sites=4, targets=5)
    data.loc[data.session >= '00006', 'detected'] = 0
    result = evaluate(data, budget=2)
    assert all(strategy['mean_coverage_pct'] is None for strategy in result['strategies'])
    assert result['coverage_vs_empirical']['logistic'] == {
        'sessions': 0, 'mean_delta_pp': None, 'bootstrap_95_ci_pp': None,
    }
    json.dumps(result, allow_nan=False)
