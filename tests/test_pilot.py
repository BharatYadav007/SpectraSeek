import csv
import json

import pytest

from spectraseek.pilot import compare, load_pilot, main


def write_pilot(path, site, seconds, backend):
    with path.open('w', newline='') as handle:
        w = csv.writer(handle)
        w.writerow(['session', 'timestamp', 'site', 'target', 'detected',
                    'signal_quality', 'backend'])
        for i, second in enumerate(seconds):
            stamp = f'2026-01-01T00:00:{second:02d}+00:00'
            w.writerow([f'{i:05d}', stamp, site, 'AP01', 1, 80, backend])
            w.writerow([f'{i:05d}', stamp, site, 'AP02', 0, '', backend])


def test_pilot_pairs_are_time_based_and_not_reused(tmp_path):
    a, b = tmp_path / 'a.csv', tmp_path / 'b.csv'
    write_pilot(a, 'S01', [0, 20, 40], 'networkmanager')
    write_pilot(b, 'S02', [19, 21, 42], 'windows')
    result = compare(a, b, max_gap_seconds=3)
    assert result['matched_pairs'] == 2
    assert result['unmatched_scans'] == [1, 1]
    assert result['pairs'][0]['left_session'] == '00001'
    assert result['pairs'][0]['right_session'] == '00000'
    assert result['scanners'][0]['targets'][1]['mean_detected_quality'] is None
    assert compare(a, b, max_gap_seconds=0)['matched_pairs'] == 0
    out = tmp_path / 'report.json'
    assert main([str(a), str(b), '--max-gap', '3', '--output', str(out)]) == 0
    assert json.loads(out.read_text()) == result


def test_pilot_rejects_incomplete_and_invalid_observations(tmp_path):
    path = tmp_path / 'pilot.csv'
    write_pilot(path, 'S01', [0, 20], 'networkmanager')
    lines = path.read_text().splitlines()
    path.write_text('\n'.join(lines[:-1]) + '\n')
    with pytest.raises(ValueError, match='inventory'):
        load_pilot(path)
    path.write_text('\n'.join(lines + [lines[-1]]) + '\n')
    with pytest.raises(ValueError, match='Duplicate'):
        load_pilot(path)
    path.write_text('\n'.join(lines).replace(',1,80,', ',1,101,') + '\n')
    with pytest.raises(ValueError, match='quality'):
        load_pilot(path)


def test_pilot_reports_normalized_timestamps_and_unmatched_records(tmp_path):
    from io import StringIO

    from spectraseek.pilot import compare_snapshots, read_pilot

    a, b = tmp_path / 'a.csv', tmp_path / 'b.csv'
    write_pilot(a, 'S01', [40, 0, 20], 'networkmanager')
    write_pilot(b, 'S02', [22, 44], 'windows-wlan')
    text = a.read_text().replace('00:00:', '05:30:').replace('+00:00', '+05:30')
    result = compare_snapshots(read_pilot(StringIO(text)), load_pilot(b), max_gap_seconds=2)
    assert result['source'] == 'measured'
    assert result['model_evaluation']['status'] == 'unsupported'
    assert result['scanners'][1]['backend'] == 'windows-wlan'
    assert result['pairs'] == [{
        'left_session': '00002', 'right_session': '00000',
        'left_timestamp': '2026-01-01T00:00:20+00:00',
        'right_timestamp': '2026-01-01T00:00:22+00:00', 'gap_seconds': 2,
    }]
    assert [[row['session'] for row in scanner]
            for scanner in result['unmatched_observations']] == [['00001', '00000'], ['00001']]
