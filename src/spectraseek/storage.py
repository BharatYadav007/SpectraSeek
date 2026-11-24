"""PostgreSQL persistence; only registered APs from authorized surveys are retained."""
import os
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy import MetaData, Table, Column, String, Float, Integer, DateTime, CheckConstraint, create_engine, select, insert
from sqlalchemy.engine import make_url
from .dataset import COLUMNS

metadata = MetaData()
scans = Table('scans', metadata, Column('session',String(100),primary_key=True), Column('site',String(100),primary_key=True), Column('captured_at',DateTime(timezone=True),nullable=False), Column('x',Float,nullable=False), Column('y',Float,nullable=False))
observations = Table('observations', metadata, Column('session',String(100),primary_key=True), Column('site',String(100),primary_key=True), Column('target',String(100),primary_key=True), Column('detected',Integer,nullable=False), Column('signal_quality',Integer), CheckConstraint('detected IN (0,1)'), CheckConstraint('(detected=0 AND signal_quality IS NULL) OR (detected=1 AND signal_quality BETWEEN 0 AND 100)'))
from sqlalchemy import ForeignKeyConstraint
observations.append_constraint(ForeignKeyConstraint(['session','site'],['scans.session','scans.site'],ondelete='CASCADE'))

class SurveyRepository:
    def __init__(self, url=None):
        url = url or os.environ.get('DATABASE_URL')
        if not url or make_url(url).drivername != 'postgresql+psycopg':
            raise ValueError('Set DATABASE_URL=postgresql+psycopg://...')
        self.engine = create_engine(url, pool_pre_ping=True)

    def initialize(self):
        metadata.create_all(self.engine)

    def record(self, session, site, x, y, targets, snapshot, min_quality=0):
        # targets maps approved BSSIDs to nonidentifying stable labels.
        import math
        if not session.strip() or not site.strip() or not targets or len(set(targets.values())) != len(targets) or not math.isfinite(x) or not math.isfinite(y) or not 0 <= min_quality <= 100:
            raise ValueError('Invalid session, site, targets, coordinates or threshold')
        seen = {mac: quality for mac, quality in snapshot.signals.items() if quality >= min_quality}
        rows = [{'session':session,'site':site,'target':label,'detected':int(mac in seen),'signal_quality':seen.get(mac)} for mac,label in targets.items()]
        with self.engine.begin() as conn:
            conn.execute(insert(scans).values(session=session,site=site,x=x,y=y,captured_at=snapshot.captured_at))
            conn.execute(insert(observations), rows)

    def export(self):
        q = select(scans.c.session,scans.c.site,observations.c.target,scans.c.x,scans.c.y,observations.c.detected).select_from(scans.join(observations)).order_by(scans.c.session,scans.c.site,observations.c.target)
        with self.engine.connect() as conn:
            return pd.read_sql(q,conn).assign(source='measured')[COLUMNS]
