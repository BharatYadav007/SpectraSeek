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
