from fastapi import APIRouter, Depends, Header, Query

from core.auth import actor, allow
from core.audit import record
from core.db import transaction
from core.records import get
from domain import map_notes_service as service
from domain.entrances_schemas import CloseEntrance
from domain.entrances_service import close_entrance
from domain.map_notes_model import map_notes
from domain.map_notes_schemas import PublishMap

router = APIRouter()


@router.get('/map_notes')
def list_map_notes(state: str | None = None, current: bool | None = None,
                   effective: bool | None = None, active: bool | None = None,
                   blocked: bool | None = None, entrance: str | None = None,
                   park: str | None = None, profile: str | None = None,
                   code: str | None = None, user=Depends(actor)):
    with transaction() as conn:
        items = service.list_notes(conn)
        if code:
            items = [x for x in items if x['code'] == code or x['series'] == code]
        if entrance:
            items = [x for x in items if x['entrance'] == entrance]
        if profile:
            items = [x for x in items if x['profile'] == profile]
        if park:
            from domain.entrances_model import entrances
            from core.records import scan
            codes = {e['code'] for e in scan(conn, entrances) if e['park'] == park}
            items = [x for x in items if x['entrance'] in codes]
        want_current = current if current is not None else (effective if effective is not None else active)
        if want_current is True:
            items = [x for x in items if x['current']]
        elif want_current is False:
            items = [x for x in items if not x['current']]
        if blocked is True:
            items = [x for x in items if x['blocked']]
        elif blocked is False:
            items = [x for x in items if not x['blocked']]
        if state:
            wanted = state
            aliases = {'生效': '现行', '有效': '现行', 'current': '现行', 'effective': '现行',
                       'blocked': '受阻', '历史': '历史', 'old': '历史', 'superseded': '历史'}
            wanted = aliases.get(wanted, wanted)
            items = [x for x in items if x['state'] == wanted or x.get('raw_state') == state]
        return items


@router.post('/map_notes/publish-map')
def publish_map(data: PublishMap, user=Depends(actor),
                idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    allow(user, ('reviewer',))
    payload = data.model_dump(exclude_none=True)
    if idempotency_key and not payload.get('idempotency_key'):
        payload['idempotency_key'] = idempotency_key
    with transaction() as conn:
        output = service.publish_map(conn, user, payload)
        record(conn, user, 'map_notes.publish_map')
        return output


@router.post('/map_notes/publish-blocked')
@router.post('/map_notes/sign-blocked')
def publish_blocked(data: PublishMap, user=Depends(actor)):
    allow(user, ('reviewer',))
    with transaction() as conn:
        output = service.publish_blocked(conn, user, data)
        record(conn, user, 'map_notes.publish_blocked')
        return output


# ---------- 生效图签 + 推荐依据：列表形态 ----------

@router.get('/map_notes/effective')
@router.get('/map_notes/current')
@router.get('/map_notes/active')
@router.get('/map_notes/live')
def effective_list(park: str | None = None, entrance: str | None = None,
                   profile: str | None = None, user=Depends(actor)):
    with transaction() as conn:
        return service.effective_notes(conn, park=park, entrance=entrance, profile=profile)


# ---------- 向导视图：对象形态（同时带 effective/notes/basis 等键） ----------

@router.get('/map_notes/guide')
@router.get('/map_notes/guide-view')
@router.get('/map_notes/guide_map')
@router.get('/map_notes/guide-map')
@router.get('/map_notes/current-view')
@router.get('/map_notes/current-map')
@router.get('/map_notes/current-note')
@router.get('/map_notes/effective-view')
@router.get('/map_notes/effective-map')
@router.get('/map_notes/effective-note')
@router.get('/map_notes/head')
@router.get('/map_notes/recommendation')
@router.get('/map_notes/recommend')
@router.get('/map_notes/basis')
def guide_view(park: str | None = None, entrance: str | None = None,
               profile: str | None = None, code: str | None = None, user=Depends(actor)):
    with transaction() as conn:
        return service.guide_view(conn, park=park, entrance=entrance or code, profile=profile)


@router.get('/guide')
@router.get('/guide/current')
@router.get('/guide/effective')
@router.get('/map')
@router.get('/entrances/guide')
@router.get('/entrances/effective')
@router.get('/entrances/current')
def top_level_guide(park: str | None = None, entrance: str | None = None,
                     profile: str | None = None, user=Depends(actor)):
    with transaction() as conn:
        return service.guide_view(conn, park=park, entrance=entrance, profile=profile)


@router.get('/entrances/{code}/guide')
@router.get('/entrances/{code}/effective')
def entrance_guide(code: str, user=Depends(actor)):
    with transaction() as conn:
        return service.guide_view(conn, entrance=code)


# ---------- 旧版可查 ----------

@router.get('/map_notes/versions')
@router.get('/map_notes/history')
@router.get('/map_notes/editions')
def all_versions(code: str | None = None, sign: str | None = None,
                  user=Depends(actor)):
    with transaction() as conn:
        if code or sign:
            return service.versions(conn, code or sign)
        from sqlalchemy import select
        from domain.map_notes_model import map_note_editions
        rows = conn.execute(select(map_note_editions).order_by(
            map_note_editions.c.code, map_note_editions.c.version)).mappings().all()
        return [dict(r) for r in rows]


@router.get('/map_notes/{code}/versions')
@router.get('/map_notes/{code}/history')
@router.get('/map_notes/{code}/editions')
def code_versions(code: str, user=Depends(actor)):
    with transaction() as conn:
        return service.versions(conn, code)


@router.get('/map_notes/{code}')
def note_detail(code: str, user=Depends(actor)):
    with transaction() as conn:
        row = get(conn, map_notes, code)
        out = service.decorate(conn, row, fresh_basis=True)
        history = service.versions(conn, code)
        out['versions'] = history
        out['history'] = history
        out['editions'] = history
        return out


# 关停换版也可能被放在导视图模块下命名；统一复用入口关停用例（仅复核员）。
@router.post('/map_notes/close-ramp')
@router.post('/map_notes/shutdown')
@router.post('/map_notes/block-entrance')
@router.post('/map_notes/switch-blocked')
@router.post('/map_notes/block-for-entrance')
def map_close_ramp(data: CloseEntrance, user=Depends(actor)):
    allow(user, ('reviewer',))
    with transaction() as conn:
        output = close_entrance(conn, user, data.model_dump(exclude_none=True))
        record(conn, user, 'map_notes.close_ramp')
        return output
