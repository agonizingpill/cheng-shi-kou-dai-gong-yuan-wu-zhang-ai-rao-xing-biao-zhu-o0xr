"""极简幂等补列：metadata.create_all 不会给旧表加列。

评测/演示通常是全新库（create_all 即得到全部列）；这里仅为沿用旧命名卷的
本地 docker 演示补齐可空列，失败不阻断启动。
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn

log = logging.getLogger('uvicorn.error')


def ensure_columns(engine, metadata):
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    dialect = engine.dialect
    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {col['name'] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present or column.primary_key:
                    continue
                try:
                    definition = str(CreateColumn(column).compile(dialect=dialect))
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {definition}'))
                    log.info('migrate: added %s.%s', table.name, column.name)
                except Exception as exc:  # 并发启动/方言差异时不致命
                    log.info('migrate skip %s.%s: %s', table.name, column.name, exc)
