"""Exercise survey transaction guarantees against an isolated PostgreSQL schema."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateSchema, DropSchema

from spectraseek.collector import ScanResult
from spectraseek.storage import SurveyRepository, observations, scans, survey_protocol
from spectraseek.survey import SurveyConfig

FIRST = '02:00:00:00:00:01'
SECOND = '02:00:00:00:00:02'
UNRELATED = '02:00:00:00:00:03'


def load_config(path, min_quality=30, targets=None, sites=None):
    path.write_text(json.dumps({
        'min_quality': min_quality,
        'sites': sites or {'S01': {'x': 0, 'y': 0}, 'S02': {'x': 2, 'y': 0}},
        'targets': targets or {FIRST: 'AP1', SECOND: 'AP2'},
    }), encoding='utf-8')
    return SurveyConfig.load(path)


@pytest.fixture
def repo():
    url = os.environ.get('SPECTRASEEK_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set SPECTRASEEK_TEST_DATABASE_URL to run PostgreSQL integration tests')
    schema = f'spectraseek_test_{uuid4().hex}'
    admin = create_engine(url)
    repository = SurveyRepository(make_url(url).update_query_dict({'options': f'-csearch_path={schema}'}))
    try:
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))
        repository.initialize()
        yield repository
    finally:
        repository.engine.dispose()
        try:
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, if_exists=True, cascade=True))
        finally:
            admin.dispose()


def test_config_normalization_and_identity(tmp_path):
    path = tmp_path / 'survey.json'
    original = load_config(path, targets={'02:00:00:00:00:0a': 'AP1', SECOND: 'AP2'})
    equivalent = load_config(
        path,
        targets={SECOND: 'AP2', '02:00:00:00:00:0A': ' AP1 '},
        sites={'S02': {'x': 2.0, 'y': -0.0}, 'S01': {'x': 0, 'y': 0}},
    )
    assert equivalent.fingerprint == original.fingerprint
    with pytest.raises(ValueError, match='min_quality'):
        load_config(path, min_quality=30.5)


def test_scan_records_approved_outcomes_and_rejects_config_changes(repo, tmp_path):
    path = tmp_path / 'survey.json'
    config = load_config(path)
    snapshot = ScanResult(datetime.now(timezone.utc), {FIRST: 70, SECOND: 20, UNRELATED: 90})
    repo.record('00001', 'S01', config, snapshot)

    with pytest.raises(IntegrityError):
        repo.record('00001', 'S01', config, snapshot)

    variants = [
        load_config(path, min_quality=40),
        load_config(path, targets={FIRST: 'AP2', SECOND: 'AP1'}),
        load_config(path, sites={'S01': {'x': 3, 'y': 0}, 'S02': {'x': 2, 'y': 0}}),
    ]
    for changed in variants:
        with pytest.raises(ValueError, match='configuration differs'):
            repo.record('00002', 'S01', changed, snapshot)
    windows_scan = ScanResult(snapshot.captured_at, snapshot.signals, backend='windows-wlan')
    with pytest.raises(ValueError, match='configuration differs'):
        repo.record('00002', 'S01', config, windows_scan)

    expected = [('00001', 'S01', 'AP1', 1), ('00001', 'S01', 'AP2', 0)]
    exported = repo.export()
    assert list(exported[['session', 'site', 'target', 'detected']].itertuples(index=False, name=None)) == expected
    with repo.engine.connect() as connection:
        qualities = connection.scalars(select(observations.c.signal_quality).order_by(observations.c.target)).all()
    assert qualities == [70, None]


def test_invalid_observation_rolls_back_scan_and_initial_protocol(repo, tmp_path):
    path = tmp_path / 'survey.json'
    config = load_config(path)
    now = datetime.now(timezone.utc)
    with pytest.raises(IntegrityError):
        repo.record('00001', 'S01', config, ScanResult(now, {FIRST: 70, SECOND: 101}))

    with repo.engine.connect() as connection:
        for table in (survey_protocol, scans, observations):
            assert connection.execute(select(table)).first() is None

    windows_scan = ScanResult(now, {FIRST: 70}, backend='windows-wlan')
    repo.record('00001', 'S01', load_config(path, min_quality=40), windows_scan)
    assert len(repo.export()) == 2


def test_existing_unverified_scans_can_be_exported_but_not_extended(repo, tmp_path):
    now = datetime.now(timezone.utc)
    with repo.engine.begin() as connection:
        connection.execute(insert(scans).values(session='old', site='S01', captured_at=now, x=0, y=0))
        connection.execute(insert(observations).values(session='old', site='S01', target='AP1', detected=0))

    config = load_config(tmp_path / 'survey.json')
    with pytest.raises(ValueError, match='no verified protocol'):
        repo.record('new', 'S01', config, ScanResult(now, {}))
    assert repo.export().session.tolist() == ['old']
    with repo.engine.connect() as connection:
        assert connection.execute(select(survey_protocol)).first() is None


def test_concurrent_first_scans_claim_only_one_protocol(repo, tmp_path):
    path = tmp_path / 'survey.json'
    left = load_config(path, min_quality=30)
    right = load_config(path, min_quality=40)
    snapshot = ScanResult(datetime.now(timezone.utc), {FIRST: 70})
    ready = Barrier(2)

    def record(session, config):
        ready.wait(timeout=10)
        try:
            repo.record(session, 'S01', config, snapshot)
        except ValueError as exc:
            assert 'configuration differs' in str(exc)
            return None
        return session

    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(record, session, config) for session, config in [('a', left), ('b', right)]]
        accepted = [session for task in tasks if (session := task.result(timeout=15)) is not None]

    assert len(accepted) == 1
    assert repo.export().session.unique().tolist() == accepted
