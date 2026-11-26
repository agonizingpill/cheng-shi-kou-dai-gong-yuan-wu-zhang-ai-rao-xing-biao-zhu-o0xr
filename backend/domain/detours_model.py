from sqlalchemy import Boolean, CheckConstraint, Column, Float, ForeignKey, Integer, JSON, String, Table

from core.db import metadata


detours = Table('detours', metadata,
    Column('code', String(64), primary_key=True),
    Column('profile', String(160), ForeignKey('walk_profiles.code'), nullable=False),
    Column('entrance', String(160), ForeignKey('entrances.code'), nullable=False),
    Column('walk_m', Integer, nullable=False),
    Column('score', Float, nullable=False),
    Column('state', String(160), nullable=False),
    CheckConstraint('walk_m between 1 and 3000'),
    CheckConstraint('score between 0 and 1'),
    # —— 关停/重走/并发版本管理的兼容列（均可空） ——
    Column('current', Boolean),
    Column('blocked', Boolean),
    Column('invalid', Boolean),
    Column('stale', Boolean),
    Column('superseded', Boolean),
    Column('retested', Boolean),
    Column('rewalked', Boolean),
    Column('fresh', Boolean),
    Column('version', Integer),
    Column('revision', Integer),
    Column('base_version', Integer),
    Column('entrance_version', Integer),
    Column('reason', String(500)),
    Column('basis', JSON),
)
