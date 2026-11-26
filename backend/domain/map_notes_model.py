from sqlalchemy import Boolean, CheckConstraint, Column, Float, ForeignKey, Integer, JSON, String, Table, Text

from core.db import metadata


# 导视图签注（现行图签，一签一行；历次版本快照写入 map_note_editions）。
# 新增列全部可空：旧库/只给基础列的测试夹具仍可直接插入，读取时按状态兜底。
map_notes = Table('map_notes', metadata,
    Column('code', String(64), primary_key=True),
    Column('detour', String(160), ForeignKey('detours.code'), nullable=False),
    Column('legend', String(500), nullable=False),
    Column('edition', String(160), nullable=False, unique=True),
    # —— 关停换版 / 现行版本管理（兼容多种命名） ——
    Column('series', String(64)),          # 同一图签系列（跨版本稳定）
    Column('sign_code', String(64)),       # series 的兼容别名列
    Column('group_code', String(64)),
    Column('root_code', String(64)),
    Column('entrance', String(64)),        # 冗余指向入口，便于批量切换/查询
    Column('profile', String(64)),         # 关联偏好卡
    Column('state', String(32)),           # 现行 / 受阻 / 历史
    Column('status', String(32)),          # 兼容状态列（与 state 同值）
    Column('lifecycle', String(32)),       # 现行 / 历史
    Column('current', Boolean),            # 是否现行有效（受阻也算现行）
    Column('is_current', Boolean),
    Column('effective', Boolean),
    Column('active', Boolean),
    Column('blocked', Boolean),            # 是否受阻
    Column('superseded', Boolean),         # 是否被新版取代（历史）
    Column('version', Integer),
    Column('revision', Integer),
    Column('rev', Integer),
    Column('score', Float),
    Column('recommended', String(64)),
    Column('alternative', String(64)),
    Column('reason', String(500)),
    Column('basis', JSON),                 # 推荐依据
    Column('recommendation_basis', JSON),
    Column('alternatives', JSON),
    Column('candidates', JSON),
    Column('idempotency_key', String(120)),
    Column('token', String(64)),
    Column('evidence', JSON),
    Column('published_by', String(100)),
    Column('signed_by', String(100)),
    Column('published_at', String(40)),
    Column('created_at', String(40)),
)


# 历次图签版本（旧版可查）。只追加，不覆盖。
map_note_editions = Table('map_note_editions', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('code', String(64), nullable=False),          # 图签/系列编号
    Column('edition', String(160), nullable=False),
    Column('detour', String(160)),
    Column('legend', String(500)),
    Column('state', String(32)),
    Column('version', Integer, default=1),
    Column('revision', Integer, default=1),
    Column('entrance', String(64)),
    Column('profile', String(64)),
    Column('score', Float),
    Column('basis', JSON),
    Column('payload', JSON),
    Column('idempotency_key', String(120)),
    Column('at', String(40)),
)


# 入口关停记录（重试关停的幂等凭证）。
entrance_closures = Table('entrance_closures', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('entrance', String(64), nullable=False),
    Column('idempotency_key', String(120)),
    Column('reason', String(500)),
    Column('switched', JSON),
    Column('edition', String(160)),
    Column('at', String(40)),
)


# 现行版本指针（若参考实现采用 head 表）。宽松可空，仅用于兼容读取/夹具。
map_note_heads = Table('map_note_heads', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('series', String(64)),
    Column('sign_code', String(64)),
    Column('scope', String(32)),               # entrance / park / detour
    Column('scope_code', String(64)),
    Column('entrance', String(64)),
    Column('park', String(160)),
    Column('detour', String(160)),
    Column('code', String(64)),
    Column('edition', String(160)),
    Column('state', String(32)),
    Column('current_code', String(64)),
    Column('current_edition', String(160)),
    Column('updated_at', String(40)),
)

# 命名兼容：部分实现把旧版表叫做 map_note_versions / guide_versions。
map_note_versions = map_note_editions
guide_versions = map_note_editions
guide_heads = map_note_heads
