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


def write_matched_rounds(left, right, *, count=16, vary=True):
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for path, site, backend, delay in (
        (left, 'S01', 'networkmanager', 3), (right, 'S02', 'windows-wlan', 5),
    ):
        with path.open('w', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['session', 'timestamp', 'site', 'target', 'detected',
                             'signal_quality', 'backend'])
            for index in range(count):
                scheduled = start + timedelta(minutes=index)
                identifier = scheduled.strftime('pilot-%Y%m%dT%H%M%SZ')
                captured = (scheduled + timedelta(seconds=delay)).isoformat()
                detected = int(vary and index % 2 == 0)
                outcomes = (1, detected) if site == 'S01' else (0, 1)
                for alias, outcome in zip(('AP01', 'AP02'), outcomes):
                    writer.writerow([identifier, captured, site, alias, outcome,
                                     70 if outcome else '', backend])


def test_scheduled_evaluation_reports_support_and_held_out_scores(tmp_path):
    left, right = tmp_path / 'a.csv', tmp_path / 'b.csv'
    write_matched_rounds(left, right)
    report = compare(left, right, verified_rounds=True)
    evaluation = report['model_evaluation']
    assert report['alignment_method'] == 'scheduled_round_and_timestamp'
    assert report['matched_pairs'] == 16
    assert evaluation['status'] == 'exploratory'
    assert (evaluation['train_rounds'], evaluation['test_rounds']) == (12, 4)
    assert evaluation['train_last_utc'] < evaluation['test_first_utc']
    assert evaluation['support']['test']['positives'] == 10
    assert set(evaluation['models']) == {'logistic', 'random_forest',
                                         'empirical_pair_frequency', 'empirical_global_frequency'}
    baseline = evaluation['models']['empirical_global_frequency']
    assert baseline['accuracy'] == 10 / 16
    assert baseline['roc_auc'] == 0.5
    assert all(result['mean_coverage_pct'] == 100
               for result in evaluation['coverage']['strategies'] if result['budget'] == 2)
    assert compare(left, right)['model_evaluation']['coverage']['status'] == 'unsupported'


def test_scheduled_alignment_does_not_pair_different_rounds(tmp_path):
    left, right = tmp_path / 'a.csv', tmp_path / 'b.csv'
    write_matched_rounds(left, right)
    lines = right.read_text().splitlines()
    right.write_text('\n'.join(lines[:1] + lines[3:]) + '\n')
    report = compare(left, right, max_gap_seconds=120)
    assert report['matched_pairs'] == 15
    assert report['unmatched_scans'] == [1, 0]
    assert all(pair['left_session'] == pair['right_session'] for pair in report['pairs'])


def test_repeated_pattern_is_not_scored(tmp_path):
    left, right = tmp_path / 'a.csv', tmp_path / 'b.csv'
    write_matched_rounds(left, right, vary=False)
    result = compare(left, right, verified_rounds=True)['model_evaluation']
    assert result['support']['train']['distinct_round_patterns'] == 1
    assert result['status'] == result['coverage']['status'] == 'unsupported'
    assert 'models' not in result


def test_pilot_purges_train_pairs_that_cross_holdout_boundary(tmp_path):
    from datetime import timedelta

    from spectraseek.pilot import match_times
    from spectraseek.pilot_evaluation import evaluate_pairs

    left, right = tmp_path / 'a.csv', tmp_path / 'b.csv'
    write_matched_rounds(left, right)
    pairs = match_times(load_pilot(left), load_pilot(right), 5)
    pairs[11][1]['timestamp'] = pairs[12][0]['timestamp'] + timedelta(seconds=1)
    evaluation = evaluate_pairs(pairs)
    assert evaluation['purged_rounds'] == 1
    assert evaluation['train_rounds'] == 11
    assert evaluation['train_last_utc'] < evaluation['test_first_utc']


def test_train_only_empirical_site_plan(tmp_path):
    left, right = tmp_path / 'a.csv', tmp_path / 'b.csv'
    write_matched_rounds(left, right)
    original = compare(left, right, verified_rounds=True)['model_evaluation']
    lines = left.read_text().splitlines()
    for index in range(25, len(lines), 2):
        lines[index] = lines[index].replace(',1,70,networkmanager', ',0,,networkmanager')
    left.write_text('\n'.join(lines) + '\n')
    altered = compare(left, right, verified_rounds=True)['model_evaluation']
    assert original['support']['test'] != altered['support']['test']
    for old, new in zip(original['coverage']['strategies'], altered['coverage']['strategies']):
        assert old['sites'] == new['sites']
