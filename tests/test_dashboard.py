from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

DASHBOARD = Path(__file__).resolve().parents[1] / 'dashboard.py'


def test_synthetic_dashboard_and_measured_empty_states():
    app = AppTest.from_file(str(DASHBOARD), default_timeout=60).run()
    assert not app.exception
    assert {metric.label for metric in app.metric} >= {'Sites', 'Held-out sessions'}
    assert any(tab.label == 'Adaptive replay' for tab in app.tabs)
    assert app.selectbox[1].options

    for mode, message in (
        ('Measured pilot', 'Upload two pilot CSVs'),
        ('Measured survey', 'Upload a complete measured survey'),
    ):
        app.sidebar.radio[0].set_value(mode).run()
        assert not app.exception
        assert any(message in info.value for info in app.info)
        assert not app.metric


@pytest.mark.parametrize('invalid_csv', [False, True])
def test_measured_pilot_dashboard(tmp_path, invalid_csv):
    from test_pilot import write_pilot

    first, second = tmp_path / 'a.csv', tmp_path / 'b.csv'
    write_pilot(first, 'S01', [1, 50], 'networkmanager')
    write_pilot(second, 'S02', [0], 'windows-wlan')
    if invalid_csv:
        second.write_text('bad,columns\n')
    app = AppTest.from_string(
        f"""import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import streamlit
files = [Path({str(first)!r}), Path({str(second)!r})]
with patch.object(streamlit.sidebar, 'radio', return_value='Measured pilot'), patch.object(
    streamlit.sidebar, 'file_uploader',
    side_effect=[SimpleNamespace(getvalue=file.read_bytes) for file in files],
):
    runpy.run_path({str(DASHBOARD)!r})
""",
        default_timeout=30,
    ).run()
    assert not app.exception
    if invalid_csv:
        assert 'Unexpected pilot CSV columns' in app.error[0].value
        assert not app.metric
        return
    assert not app.error
    assert {metric.label: metric.value for metric in app.metric} == {
        'S01 scans': '2', 'S02 scans': '1', 'Candidate pairs': '1', 'Unmatched scans': '1',
    }
    assert any('shared target identity' in warning.value for warning in app.warning)
