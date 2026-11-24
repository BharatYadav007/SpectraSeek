import csv
from datetime import datetime, timedelta, timezone

import pytest

from spectraseek import pilot_collection
from spectraseek.collector import ScanResult
from spectraseek.pilot import load_pilot
from spectraseek.survey import SurveyConfig


def test_collection_preserves_common_schedule_and_omits_failed_round(monkeypatch, tmp_path):
    config = SurveyConfig.load('examples/survey.example.json')
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    starts = []

    def wait(seconds):
        nonlocal now
        now += timedelta(seconds=seconds)

    def scan(interface):
        assert interface == 'Lab adapter'
        starts.append(now)
        wait(1)
        if len(starts) == 2:
            raise RuntimeError('backend failure')
        return ScanResult(now, {'02:00:00:00:00:01': 72, '02:00:00:00:00:03': 61},
                          'windows-wlan')

    start = now + timedelta(seconds=10)
    monkeypatch.setattr(pilot_collection, 'scan', scan)
    output = tmp_path / 'measured_pilot.csv'
    options = {'clock': lambda: now, 'wait': wait}
    assert pilot_collection.collect(config, 'S01', start, 3, 60, output,
                                    'Lab adapter', **options) == 2
    assert starts == [start + timedelta(minutes=index) for index in range(3)]
    observations = load_pilot(output)
    assert [row['session'] for row in observations] == ['pilot-20260101T000010Z',
                                                         'pilot-20260101T000210Z']
    assert observations[0]['timestamp'] == start + timedelta(seconds=1)
    assert observations[0]['targets'] == {'AP01': 72, 'AP02': None}
    assert observations[0]['backend'] == 'windows-wlan'
    with output.open(newline='') as handle:
        assert len(list(csv.DictReader(handle))) == 4
    with pytest.raises(FileExistsError):
        pilot_collection.collect(config, 'S01', now + timedelta(seconds=5), 3, 60, output,
                                 **options)


def test_pilot_collect_cli_requires_authorization_and_passes_schedule(monkeypatch, tmp_path):
    from spectraseek.cli import main

    captured = []

    def fake_collect(config, site, start, rounds, interval, path, interface):
        captured.append((site, start, rounds, interval, path, interface))
        return rounds

    monkeypatch.setattr(pilot_collection, 'collect', fake_collect)
    output = str(tmp_path / 'pilot.csv')
    args = ['pilot-collect', '--config', 'examples/survey.example.json', '--site', 'S01',
            '--start', '2026-01-01T00:00:00+00:00', '--interface', 'Lab adapter',
            '--rounds', '16', '--interval', '60', '--output', output]
    with pytest.raises(SystemExit):
        main(args)
    assert not captured
    assert main([*args, '--authorized']) == 0
    assert captured == [('S01', datetime(2026, 1, 1, tzinfo=timezone.utc), 16, 60,
                         output, 'Lab adapter')]
