from sqlalchemy import select

from core.records import get, insert, need, scan, update
from domain.entrances_model import entrances
from domain.map_notes_model import entrance_closures
from domain import map_notes_service
from domain.map_notes_service import now, switch_for_entrance


def _already_closed_record(conn, code, idem_key=None):
    query = select(entrance_closures).where(entrance_closures.c.entrance == code)
    if idem_key:
        query = query.where(entrance_closures.c.idempotency_key == idem_key)
    row = conn.execute(query.order_by(entrance_closures.c.id.desc())).mappings().first()
    return dict(row) if row else None


def close_entrance(conn, user, data):
    """关停坡道：一次性把指向它的现行图签切为受阻。

    重试（坡道已是关停态，或命中同一幂等键）只回读结果，不重复换版。
    """
    payload = data if isinstance(data, dict) else data.model_dump(exclude_none=True)
    code = payload.get('entrance') or payload.get('code') or payload.get('entrance_code')
    idem_key = payload.get('idempotency_key') or payload.get('request_key')
    reason = payload.get('reason')
    row = get(conn, entrances, code, lock=True)

    prior = _already_closed_record(conn, code, idem_key)
    already_down = row['ramp'] is False or row.get('closed') is True or row.get('shutdown') is True

    if prior is not None or already_down:
        summary = switch_for_entrance(conn, row, reason=reason, idem_key=idem_key)
        current = get(conn, entrances, code)
        guide = map_notes_service.guide_view(conn, entrance=code)
        primary = guide.get('current')
        return {**current, 'closed': True, 'retried': True, 'idempotent': True,
                'state': '受阻', 'result_state': '受阻',
                'note': primary, 'map_note': primary, 'current_note': primary,
                'switched': [], 'already_blocked': summary['switched'] + summary['already_blocked'],
                'notes': guide.get('effective'),
                'map_notes': guide.get('effective'),
                'count': summary['count'],
                'basis': guide.get('basis'), 'recommendation_basis': guide.get('basis'),
                'recommended': guide.get('recommended'),
                'alternatives': guide.get('alternatives'),
                'effective': guide.get('effective')}

    version = int(row.get('version') or row.get('revision') or 1) + 1
    update(conn, entrances, code, ramp=False, condition='现场见证',
           closed=True, shutdown=True, blocked=True, available=False, passable=False,
           version=version, revision=version, close_reason=reason)
    latest = get(conn, entrances, code)
    summary = switch_for_entrance(conn, latest, reason=reason, idem_key=idem_key,
                                 new_edition=payload.get('edition') or payload.get('new_edition'))
    insert(conn, entrance_closures, entrance=code, idempotency_key=idem_key,
           reason=reason, switched=summary['switched'],
           edition=payload.get('edition') or payload.get('new_edition'), at=now())
    guide = map_notes_service.guide_view(conn, entrance=code)
    primary = guide.get('current')
    return {**latest, 'closed': True, 'retried': False, 'idempotent': False,
            'state': '受阻', 'result_state': '受阻',
            'note': primary, 'map_note': primary, 'current_note': primary,
            'switched': summary['switched'], 'already_blocked': summary['already_blocked'],
            'notes': guide.get('effective'), 'map_notes': guide.get('effective'),
            'count': summary['count'],
            'basis': guide.get('basis'), 'recommendation_basis': guide.get('basis'),
            'recommended': guide.get('recommended'),
            'alternatives': guide.get('alternatives'),
            'effective': guide.get('effective')}


def inspect(conn, user, data):
    row = get(conn, entrances, data.entrance, lock=True)
    old_ramp = row['ramp']
    new_ramp = data.ramp
    version = int(row.get('version') or row.get('revision') or 1) + 1
    values = dict(ramp=new_ramp, condition='现场见证', version=version, revision=version)
    if new_ramp is False:
        values.update(closed=True, shutdown=True, blocked=True, available=False, passable=False)
    else:
        values.update(closed=False, shutdown=False, blocked=False, available=True, passable=True)
    output = update(conn, entrances, data.entrance, **values)

    # 现场复查把坡道从可通行改为关停 => 同一事务内批量切换现行图签。
    if old_ramp is True and new_ramp is False:
        summary = switch_for_entrance(conn, output, reason='入口复查确认坡道关停')
        guide = map_notes_service.guide_view(conn, entrance=data.entrance)
        primary = guide.get('current')
        output.update({
            'closed': True, 'state': '受阻', 'result_state': '受阻',
            'retried': False, 'idempotent': False,
            'switched': summary['switched'],
            'already_blocked': summary['already_blocked'],
            'count': summary['count'],
            'note': primary, 'map_note': primary,
            'basis': guide.get('basis'), 'recommendation_basis': guide.get('basis'),
            'recommended': guide.get('recommended'),
            'alternatives': guide.get('alternatives'),
            'effective': guide.get('effective')})
    return output
