from sqlalchemy import Boolean, CheckConstraint, Column, Float, ForeignKey, Integer, JSON, String, Table

from core.db import metadata


entrances = Table('entrances', metadata,
    Column('code', String(64), primary_key=True),
    Column('park', String(160), nullable=False),
    Column('ramp', Boolean, nullable=False),
    Column('tags', JSON, nullable=False),
    Column('condition', String(160), nullable=False),
    # —— 关停/并发版本管理（均可空，旧夹具直接插入不受影响） ——
    Column('closed', Boolean),
    Column('shutdown', Boolean),
    Column('blocked', Boolean),
    Column('available', Boolean),
    Column('passable', Boolean),
    Column('version', Integer),
    Column('revision', Integer),
    Column('base_version', Integer),
    Column('status', String(32)),
    Column('close_reason', String(500)),
    Column('closed_at', String(40)),
)
