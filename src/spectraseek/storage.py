"""Persist observations for one authorized survey protocol per PostgreSQL database."""

from hashlib import sha256
import os

import pandas as pd
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, URL, make_url

from .collector import ScanResult
from .dataset import COLUMNS
from .survey import SurveyConfig, survey_id

metadata = MetaData()
survey_protocol = Table(
    'survey_protocol',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=False),
    Column('fingerprint', String(64), nullable=False),
    CheckConstraint('id = 1'),
)
scans = Table(
    'scans',
    metadata,
    Column('session', String(100), primary_key=True),
    Column('site', String(100), primary_key=True),
    Column('captured_at', DateTime(timezone=True), nullable=False),
    Column('x', Float, nullable=False),
    Column('y', Float, nullable=False),
)
observations = Table(
    'observations',
    metadata,
    Column('session', String(100), primary_key=True),
    Column('site', String(100), primary_key=True),
    Column('target', String(100), primary_key=True),
    Column('detected', Integer, nullable=False),
    Column('signal_quality', Integer),
    CheckConstraint('detected IN (0,1)'),
    CheckConstraint(
        '(detected = 0 AND signal_quality IS NULL) OR '
        '(detected = 1 AND signal_quality IS NOT NULL AND signal_quality BETWEEN 0 AND 100)'
    ),
    ForeignKeyConstraint(['session', 'site'], ['scans.session', 'scans.site'], ondelete='CASCADE'),
)


def _check_protocol(connection: Connection, fingerprint: str) -> None:
    # A concurrent first scan must wait for the winning transaction to commit or roll back.
    claim = (
        pg_insert(survey_protocol)
        .values(id=1, fingerprint=fingerprint)
        .on_conflict_do_nothing(index_elements=[survey_protocol.c.id])
        .returning(survey_protocol.c.id)
    )
    if connection.execute(claim).scalar_one_or_none() is not None:
        if connection.scalar(select(select(scans.c.session).exists())):
            raise ValueError('Existing scans have no verified protocol. Export them and use a fresh database for new scans.')
        return

    stored = connection.execute(select(survey_protocol.c.fingerprint)).scalar_one()
    if stored != fingerprint:
        raise ValueError('Survey configuration differs from existing scans. Use a fresh database when changing the survey or collector.')


class SurveyRepository:
    def __init__(self, url: str | URL | None = None):
        url = url or os.environ.get('DATABASE_URL')
        if not url or make_url(url).drivername != 'postgresql+psycopg':
            raise ValueError('Set DATABASE_URL=postgresql+psycopg://...')
        self.engine = create_engine(url, pool_pre_ping=True)

    def initialize(self) -> None:
        metadata.create_all(self.engine)

    def record(self, session: str, site: str, config: SurveyConfig, snapshot: ScanResult) -> None:
        session = survey_id(session)
        site = survey_id(site)
        if site not in config.sites:
            raise ValueError(f'Unknown survey site: {site}')
        x, y = config.sites[site]
        rows = []
        for address, label in config.targets.items():
            quality = snapshot.signals.get(address)
            if quality is not None and quality < config.min_quality:
                quality = None
            rows.append({
                'session': session,
                'site': site,
                'target': label,
                'detected': int(quality is not None),
                'signal_quality': quality,
            })

        fingerprint = config.fingerprint
        if snapshot.backend != 'networkmanager':
            # Keep the original fingerprint for databases created by the Linux collector.
            fingerprint = sha256(f'{snapshot.backend}:{fingerprint}'.encode('utf-8')).hexdigest()

        with self.engine.begin() as connection:
            _check_protocol(connection, fingerprint)
            connection.execute(insert(scans).values(
                session=session, site=site, x=x, y=y, captured_at=snapshot.captured_at,
            ))
            connection.execute(insert(observations), rows)

    def export(self) -> pd.DataFrame:
        query = select(
            scans.c.session, scans.c.site, observations.c.target,
            scans.c.x, scans.c.y, observations.c.detected,
        ).select_from(scans.join(observations)).order_by(
            scans.c.session, scans.c.site, observations.c.target,
        )
        with self.engine.connect() as connection:
            return pd.read_sql(query, connection).assign(source='measured')[COLUMNS]
