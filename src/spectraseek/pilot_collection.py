"""Collect approved Wi-Fi observations on a common absolute UTC schedule."""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
from time import sleep

from .collector import scan
from .survey import SurveyConfig

PILOT_FIELDS = ('session', 'timestamp', 'site', 'target', 'detected', 'signal_quality', 'backend')
ROUND_PREFIX = 'pilot-'
ROUND_FORMAT = ROUND_PREFIX + '%Y%m%dT%H%M%SZ'
CAPTURE_SECONDS = 45


def round_start(session):
    try:
        start = datetime.strptime(session, ROUND_FORMAT).replace(tzinfo=timezone.utc)
        if start.strftime(ROUND_FORMAT) == session:
            return start
    except ValueError:
        pass
    raise ValueError('Verified rounds require scheduled pilot session IDs from pilot-collect')


def collect(config, site, start, rounds, interval, path, interface=None, *,
            clock=lambda: datetime.now(timezone.utc), wait=sleep):
    if site not in config.sites:
        raise ValueError('Select a site registered in the shared survey configuration')
    if start.utcoffset() is None or start.microsecond:
        raise ValueError('Use an offset-aware start timestamp with whole seconds')
    start = start.astimezone(timezone.utc)
    if start <= clock():
        raise ValueError('The shared start time must be in the future')
    if rounds < 1 or interval < 60:
        raise ValueError('Use at least one round and an interval of at least 60 seconds')

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    with output.open('x', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(PILOT_FIELDS)
        handle.flush()
        for index in range(rounds):
            scheduled = start + timedelta(seconds=index * interval)
            deadline = scheduled + timedelta(seconds=CAPTURE_SECONDS)
            current = clock()
            while current < scheduled:
                wait(min(5, (scheduled - current).total_seconds()))
                current = clock()
            session = scheduled.strftime(ROUND_FORMAT)
            if current >= deadline:
                print(f'{session}: missed collection window', file=sys.stderr)
                continue
            try:
                result = scan(interface)
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
                print(f'{session}: scanner error; round omitted', file=sys.stderr)
                continue
            if not current <= result.captured_at <= deadline:
                print(f'{session}: scan timestamp outside the collection window', file=sys.stderr)
                continue
            writer.writerows(
                (session, result.captured_at.astimezone(timezone.utc).isoformat(), site, alias,
                 int(quality >= config.min_quality), quality if quality >= config.min_quality else '',
                 result.backend)
                for address, alias in sorted(config.targets.items(), key=lambda item: item[1])
                for quality in (result.signals.get(address, -1),)
            )
            handle.flush()
            completed += 1
            print(f'{session}: recorded {site}', flush=True)
    return completed


def run(args):
    config = SurveyConfig.load(args.config)
    completed = collect(config, args.site, datetime.fromisoformat(args.start), args.rounds,
                        args.interval, args.output, args.interface)
    print(f'Recorded {completed}/{args.rounds} scheduled rounds')
    return 0 if completed else 1
