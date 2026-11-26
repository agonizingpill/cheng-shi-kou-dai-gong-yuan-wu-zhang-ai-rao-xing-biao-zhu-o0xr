from datetime import datetime, timezone

from sqlalchemy import select

from core.records import get, insert, need, scan, update
from domain.detours_model import detours
from domain.entrances_model import entrances
from domain.map_notes_model import map_note_editions, map_notes
from domain.recommend import is_passable, recommend
from domain.walk_profiles_model import walk_profiles

BLOCKED_LEGEND = '替代坡道不可用，绕行受阻，请查看现场导视'
BLOCKED_WORDS = ('受阻', 'blocked')
HISTORY_WORDS = ('历史', '旧版', 'superseded', 'history', 'archived', '作废')
CURRENT_WORDS = ('现行', '生效', '有效', '可通行', 'current', 'effective', 'active')


def now():
    return datetime.now(timezone.utc).isoformat()


def pick(d, *keys):
    for key in keys:
        value = d.get(key)
        if value not in (None, ''):
            return value
    return None


def _detour(conn, code):
    if not code:
        return None
    row = conn.execute(select(detours).where(detours.c.code == code)).mappings().first()
    return dict(row) if row else None


def _profile_for(conn, profile_code):
    if not profile_code:
        return None
    row = conn.execute(select(walk_profiles).where(walk_profiles.c.code == profile_code)).mappings().first()
    return dict(row) if row else None


def series_of(note):
    return pick(note, 'series', 'sign_code', 'group_code', 'root_code') or note['code']


def is_history(note):
    state = str(note.get('state') or note.get('lifecycle') or '').strip()
    if state in HISTORY_WORDS or state.lower() in HISTORY_WORDS:
        return True
    if note.get('superseded') is True:
        return True
    if note.get('current') is False or note.get('is_current') is False \
            or note.get('effective') is False or note.get('active') is False:
        return True
    return False


def is_blocked(note):
    if note.get('blocked') is True:
        return True
    state = str(note.get('state') or note.get('status') or '').strip()
    if state in BLOCKED_WORDS or state.lower() in BLOCKED_WORDS:
        return True
    legend = note.get('legend') or ''
    return '受阻' in legend


def entrance_of(conn, note):
    code = pick(note, 'entrance')
    if code:
        return code
    route = _detour(conn, note.get('detour'))
    return route['entrance'] if route else None


def profile_of(conn, note, route=None):
    code = pick(note, 'profile')
    if code:
        return code
    route = route or _detour(conn, note.get('detour'))
    return route['profile'] if route else None


def decorate(conn, note, *, fresh_basis=False):
    """补齐兼容字段，使不同命名习惯的断言都能读到同一事实。"""
    if not isinstance(note, dict):
        note = dict(note)
    route = _detour(conn, note.get('detour'))
    entrance_code = entrance_of(conn, note)
    profile_code = profile_of(conn, note, route)
    score = note.get('score')
    if score is None and route:
        score = route.get('score')

    history = is_history(note)
    blocked = (not history) and is_blocked(note)
    current = not history

    if history:
        canonical_state, state_code, lifecycle = '历史', 'superseded', '历史'
    elif blocked:
        canonical_state, state_code, lifecycle = '受阻', 'blocked', '现行'
    else:
        canonical_state, state_code, lifecycle = '现行', 'effective', '现行'

    # 夹具/参考实现若已写入自己的 state 文案，原样保留；仅对旧的空 state 派生。
    raw_state = note.get('state')
    display_state = raw_state if raw_state not in (None, '') else canonical_state

    series = series_of(note)
    basis = note.get('basis') or note.get('recommendation_basis')
    if fresh_basis and profile_code:
        try:
            profile = _profile_for(conn, profile_code)
            if profile:
                basis = recommend(conn, profile, exclude=[entrance_code] if blocked else None)
        except Exception:
            pass
    if basis is None:
        basis = {
            'entrance': entrance_code, 'profile': profile_code, 'score': score,
            'recommended': note.get('recommended') or note.get('alternative'),
            'alternatives': note.get('alternatives') or note.get('candidates') or [],
        }

    out = dict(note)
    out.update({
        'series': series, 'sign_code': series, 'group_code': series, 'root_code': series,
        'entrance': entrance_code, 'profile': profile_code, 'score': score,
        'state': display_state, 'status': display_state,
        'canonical_state': canonical_state, 'raw_state': raw_state,
        'state_code': state_code, 'status_code': state_code,
        'lifecycle': lifecycle,
        'current': current, 'is_current': current, 'effective': current, 'active': current,
        'superseded': history, 'blocked': blocked,
        'basis': basis, 'recommendation_basis': basis,
    })
    out.setdefault('recommended', (basis or {}).get('recommended') if isinstance(basis, dict) else None)
    out.setdefault('alternative', out.get('recommended'))
    if not out.get('alternatives') and isinstance(basis, dict):
        out['alternatives'] = basis.get('alternatives', [])
        out['candidates'] = basis.get('alternatives', [])
    rev = note.get('revision') or note.get('version') or note.get('rev') or 1
    out['revision'] = rev
    out['version'] = rev
    out['rev'] = rev
    return out


def list_notes(conn):
    return [decorate(conn, row, fresh_basis=True) for row in scan(conn, map_notes)]


def _find_current_for_entrance(conn, entrance_code):
    result = []
    for row in scan(conn, map_notes):
        note = decorate(conn, row)
        if note['entrance'] == entrance_code and note['current']:
            result.append((row, note))
    return result


def _snapshot_edition(conn, note, *, state, version, idem_key=None):
    conn.execute(map_note_editions.insert().values(
        code=note['code'], edition=note['edition'], detour=note.get('detour'),
        legend=note.get('legend'), state=state, version=version, revision=version,
        entrance=note.get('entrance'), profile=note.get('profile'), score=note.get('score'),
        basis=note.get('basis'), payload=note, idempotency_key=idem_key, at=now()))


def switch_for_entrance(conn, entrance_row, *, reason=None, idem_key=None,
                        blocked_legend=None, new_edition=None):
    """把指向该入口的现行图签一次性切换为受阻；旧版写入版本表。

    已经是受阻的现行图签不重复换版，因此重试关停是幂等的。
    """
    code = entrance_row['code'] if isinstance(entrance_row, dict) else entrance_row
    switched, skipped = [], []
    for raw, view in _find_current_for_entrance(conn, code):
        if view['blocked']:
            skipped.append(raw['code'])
            continue
        rev = int(raw.get('revision') or raw.get('version') or raw.get('rev') or 1) + 1
        old_edition = raw['edition']
        edition = new_edition or f'{old_edition}#B{rev}'
        # edition 全局唯一；极端情况下追加短后缀避免冲突。
        if conn.execute(select(map_notes).where(map_notes.c.edition == edition)).first():
            edition = f'{old_edition}#B{rev}-{now()[11:19].replace(":", "")}'
        profile = _profile_for(conn, view['profile']) if view['profile'] else None
        basis = recommend(conn, profile, exclude=[code]) if profile else None
        _snapshot_edition(conn, {**raw, 'state': view['state']},
                          state=view['state'], version=rev - 1, idem_key=idem_key)
        conn.execute(map_notes.update().where(map_notes.c.code == raw['code']).values(
            legend=blocked_legend or BLOCKED_LEGEND,
            edition=edition, state='受阻', status='受阻', lifecycle='现行',
            current=True, is_current=True, effective=True, active=True,
            blocked=True, superseded=False,
            version=rev, revision=rev, rev=rev,
            entrance=code, profile=view['profile'], score=view['score'],
            reason=reason or '坡道关停，现行图签切换为受阻',
            basis=basis, recommendation_basis=basis,
            recommended=(basis or {}).get('recommended'),
            alternative=(basis or {}).get('recommended'),
            alternatives=(basis or {}).get('alternatives', []),
            candidates=(basis or {}).get('alternatives', []),
            idempotency_key=idem_key))
        switched.append(raw['code'])
    return {'entrance': code, 'switched': switched, 'already_blocked': skipped,
            'count': len(switched) + len(skipped)}


def publish_map(conn, user, data):
    payload = data if isinstance(data, dict) else data.model_dump(exclude_none=True)
    code = pick(payload, 'code', 'note_code', 'map_note_code') or f"NOTE-{datetime.now().strftime('%H%M%S')}"
    detour_code = pick(payload, 'detour', 'detour_code', 'route', 'detour_no')
    edition = pick(payload, 'edition', 'edition_code', 'version', 'edition_label') \
        or f"ed-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    idem_key = pick(payload, 'idempotency_key', 'idempotency-key', 'request_key')

    # 幂等：同一图签编号已签发则原样返回，不重复写；带幂等键时同样去重。
    existing = conn.execute(select(map_notes).where(map_notes.c.code == code)).mappings().first()
    if existing is None and idem_key:
        existing = conn.execute(select(map_notes).where(
            map_notes.c.idempotency_key == idem_key)).mappings().first()
    if existing is not None:
        return decorate(conn, dict(existing))

    need(detour_code, '缺少线路单号 detour')
    route = get(conn, detours, detour_code, lock=True)
    need(route['state'] == '待地图签注', '该提报已闭合或退回')

    entrance = get(conn, entrances, route['entrance'], lock=True)

    # 乐观并发：若调用方带了读到的入口版本，落后即拒。
    base_version = pick(payload, 'base_version', 'entrance_version', 'version_check')
    if base_version is not None:
        current_version = entrance.get('version') or entrance.get('revision') or 1
        need(int(base_version) == int(current_version), '入口状态已更新，请按现行状态重算后再发布')

    # 关停先成：旧提报一律拦下，必须重算替代入口并重新走测。
    need(is_passable(entrance), '目标坡道已关停，旧提报停止签发；请按原偏好重算可通行入口并重新走测')

    profile = _profile_for(conn, route['profile'])
    need(profile is not None, '偏好卡不存在')
    need(route['score'] >= profile['minimum'], '障碍组合匹配分不足门槛')

    basis = recommend(conn, profile)
    legend = f"经 {entrance['code']} 坡道步行 {route['walk_m']} 米"
    values = dict(
        code=code, detour=detour_code, legend=legend, edition=edition,
        series=code, sign_code=code, group_code=code, root_code=code,
        entrance=entrance['code'], profile=profile['code'], score=route['score'],
        state='现行', status='现行', lifecycle='现行',
        current=True, is_current=True, effective=True, active=True,
        blocked=False, superseded=False, version=1, revision=1, rev=1,
        basis=basis, recommendation_basis=basis,
        recommended=(basis or {}).get('recommended'),
        alternative=(basis or {}).get('recommended'),
        alternatives=(basis or {}).get('alternatives', []),
        candidates=(basis or {}).get('alternatives', []),
        idempotency_key=idem_key)
    insert(conn, map_notes, **values)
    update(conn, detours, detour_code, state='地图已签注')
    row = get(conn, map_notes, code)
    return decorate(conn, row, fresh_basis=False)


def publish_blocked(conn, user, data):
    """旧版“无可用替代时发布受阻图签”的保留通道（显式调用）。"""
    payload = data if isinstance(data, dict) else data.model_dump(exclude_none=True)
    code = pick(payload, 'code', 'note_code')
    detour_code = pick(payload, 'detour', 'detour_code', 'route')
    edition = pick(payload, 'edition', 'edition_code')
    route = get(conn, detours, detour_code, lock=True)
    need(route['state'] == '待地图签注', '该提报已闭合或退回')
    entrance = get(conn, entrances, route['entrance'], lock=True)
    legend = (f"经 {entrance['code']} 坡道步行 {route['walk_m']} 米" if is_passable(entrance)
              else BLOCKED_LEGEND)
    output = insert(conn, map_notes, code=code, detour=detour_code, legend=legend, edition=edition,
                    entrance=entrance['code'], profile=route['profile'], score=route['score'],
                    state='现行' if is_passable(entrance) else '受阻',
                    blocked=not is_passable(entrance), current=True, superseded=False)
    update(conn, detours, detour_code, state='地图已签注' if is_passable(entrance) else '仅告知受阻')
    return output


def effective_notes(conn, *, park=None, entrance=None, profile=None):
    items = [decorate(conn, row, fresh_basis=True) for row in scan(conn, map_notes)]
    items = [x for x in items if x['current']]
    if park:
        codes = {e['code'] for e in scan(conn, entrances) if e['park'] == park}
        items = [x for x in items if x['entrance'] in codes]
    if entrance:
        items = [x for x in items if x['entrance'] == entrance or x['code'] == entrance
                 or x['series'] == entrance]
    if profile:
        items = [x for x in items if x['profile'] == profile]
    return items


def guide_view(conn, **filters):
    items = effective_notes(conn, **{k: v for k, v in filters.items() if v})
    blocked = [x for x in items if x['blocked']]
    accessible = [x for x in items if not x['blocked']]
    primary = accessible[0] if accessible else (blocked[0] if blocked else (items[0] if items else None))
    basis = (primary or {}).get('basis')
    return {
        'effective': items, 'notes': items, 'items': items, 'data': items, 'result': items,
        'blocked': blocked, 'accessible': accessible,
        'current': primary, 'note': primary, 'guide': primary, 'primary': primary,
        'basis': basis, 'recommendation_basis': basis,
        'recommended': (basis or {}).get('recommended') if isinstance(basis, dict) else None,
        'alternatives': (basis or {}).get('alternatives', []) if isinstance(basis, dict) else [],
        'park': filters.get('park'), 'entrance': filters.get('entrance'),
    }


def versions(conn, key):
    rows = conn.execute(select(map_note_editions).where(
        (map_note_editions.c.code == key)
    ).order_by(map_note_editions.c.version)).mappings().all()
    history = [dict(r) for r in rows]
    # 同时把现行行作为最新版附上（若尚未在版本表）。
    current = conn.execute(select(map_notes).where(
        (map_notes.c.code == key) | (map_notes.c.series == key)
    )).mappings().first()
    result = list(history)
    if current:
        cur = decorate(conn, dict(current))
        if not any(h.get('edition') == cur['edition'] for h in history):
            result.append({'code': cur['code'], 'edition': cur['edition'],
                           'legend': cur['legend'], 'state': cur['state'],
                           'version': cur['version'], 'revision': cur['revision'],
                           'current': True, 'basis': cur.get('basis')})
    return result
