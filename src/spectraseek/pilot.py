"""Validate and compare two independent authorized survey pilot CSVs.

Timestamp alignment is exploratory, not evidence of synchronized sessions.
No raw BSSIDs are collected or exported here.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean

FIELDS = {'session', 'timestamp', 'site', 'target', 'detected',
          'signal_quality', 'backend'}


def load_pilot(path):
    """Return a chronological list of complete observation snapshots."""
    groups = {}
    with open(path, encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if len(reader.fieldnames or []) != len(FIELDS) or set(reader.fieldnames or []) != FIELDS:
            raise ValueError('Unexpected pilot CSV columns')
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Malformed pilot CSV row')
            session, site, target, backend = (
                row[k].strip() for k in ('session', 'site', 'target', 'backend')
            )
            if not all((session, site, target, backend)):
                raise ValueError('Empty pilot identifier')
            stamp = datetime.fromisoformat(row['timestamp'])
            if stamp.utcoffset() is None:
                raise ValueError('Pilot timestamps must include a UTC offset')
            stamp = stamp.astimezone(timezone.utc)
            if row['detected'] not in ('0', '1'):
                raise ValueError('Detection must be 0 or 1')
            detected = int(row['detected'])
            q = int(row['signal_quality']) if row['signal_quality'] else None
            if (q is None) != (detected == 0) or (q is not None and not 0 <= q <= 100):
                raise ValueError('Signal quality inconsistent with detection')
            snapshot = groups.setdefault(session, {
                'session': session, 'timestamp': stamp, 'site': site,
                'backend': backend, 'targets': {},
            })
            if (snapshot['timestamp'], snapshot['site'], snapshot['backend']) != (stamp, site, backend):
                raise ValueError('Inconsistent snapshot metadata')
            if target in snapshot['targets']:
                raise ValueError('Duplicate target observation')
            snapshot['targets'][target] = q
    snapshots = sorted(groups.values(), key=lambda s: s['timestamp'])
    if not snapshots:
        raise ValueError('Empty pilot CSV')
    if len({(s['site'], s['backend']) for s in snapshots}) != 1:
        raise ValueError('Each pilot file must use one site and backend')
    if len({s['timestamp'] for s in snapshots}) != len(snapshots):
        raise ValueError('Repeated snapshot timestamp')
    inventory = set(snapshots[0]['targets'])
    if any(set(s['targets']) != inventory for s in snapshots):
        raise ValueError('Incomplete or inconsistent target inventory')
    return snapshots


def match_times(left, right, max_gap_seconds):
    """Match earliest feasible snapshots in order, at most once each."""
    if not 0 <= max_gap_seconds <= 300:
        raise ValueError('Timestamp tolerance must be between 0 and 300 seconds')
    i = j = 0
    pairs = []
    while i < len(left) and j < len(right):
        gap = (left[i]['timestamp'] - right[j]['timestamp']).total_seconds()
        if abs(gap) <= max_gap_seconds:
            pairs.append((left[i], right[j], abs(gap)))
            i += 1
            j += 1
        elif gap < 0:
            i += 1
        else:
            j += 1
    return pairs


def describe(snapshots):
    result = []
    for target in sorted(snapshots[0]['targets']):
        values = [s['targets'][target] for s in snapshots]
        seen = [q for q in values if q is not None]
        result.append({
            'target': target, 'scans': len(values), 'detected': len(seen),
            'detection_rate': len(seen) / len(values),
            'mean_detected_quality': mean(seen) if seen else None,
        })
    return {'site': snapshots[0]['site'], 'backend': snapshots[0]['backend'],
            'scans': len(snapshots), 'targets': result}


def compare(left_path, right_path, *, max_gap_seconds=30):
    left, right = load_pilot(left_path), load_pilot(right_path)
    if left[0]['site'] == right[0]['site']:
        raise ValueError('Pilot files must represent distinct sites')
    if set(left[0]['targets']) != set(right[0]['targets']):
        raise ValueError('Pilot target aliases differ')
    pairs = match_times(left, right, max_gap_seconds)
    return {
        'analysis': 'exploratory_pilot_only',
        'limitations': [
            'Matching timestamps does not verify clock synchronization or target identity.',
            'Site and scanner effects may be confounded; signal quality is not calibrated.',
            'No paired training dataset or controlled performance claim is produced.',
        ],
        'max_gap_seconds': max_gap_seconds,
        'scanners': [describe(left), describe(right)],
        'matched_pairs': len(pairs),
        'unmatched_scans': [len(left) - len(pairs), len(right) - len(pairs)],
        'max_observed_gap_seconds': max((g for _, _, g in pairs), default=None),
        'mean_observed_gap_seconds': mean(g for _, _, g in pairs) if pairs else None,
        'pairs': [
            {'left_session': a['session'], 'right_session': b['session'],
             'gap_seconds': g} for a, b, g in pairs
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('left_csv')
    parser.add_argument('right_csv')
    parser.add_argument('--max-gap', type=float, default=30)
    parser.add_argument('--output', default='results/pilot.local.json')
    args = parser.parse_args(argv)
    try:
        report = compare(args.left_csv, args.right_csv, max_gap_seconds=args.max_gap)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Error: {exc}\n')
    print(f'Saved {output}: {report["matched_pairs"]} candidate pairs')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
