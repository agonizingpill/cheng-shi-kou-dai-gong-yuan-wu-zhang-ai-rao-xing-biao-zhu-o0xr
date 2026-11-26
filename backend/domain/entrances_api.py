from fastapi import APIRouter, Depends, Header

from core.auth import actor, allow
from core.audit import record
from core.db import transaction
from core.records import get, scan
from domain import entrances_service as service
from domain.entrances_model import entrances
from domain.entrances_schemas import CloseEntrance, Inspect

router = APIRouter()

def _normalized_inspect(payload, conn=None):
    data = payload or {}
    code = data.get('entrance') or data.get('code') or data.get('entrance_code')
    if 'ramp' in data and data['ramp'] is not None:
        ramp = bool(data['ramp'])
    elif data.get('closed') or data.get('shutdown') or data.get('blocked'):
        ramp = False
    elif data.get('open') or data.get('passable') or data.get('available'):
        ramp = True
    elif conn is not None and code:
        ramp = get(conn, entrances, code)['ramp']
    else:
        ramp = True
    return Inspect(entrance=code, ramp=ramp, reason=data.get('reason'),
                   idempotency_key=data.get('idempotency_key'))


@router.get('/entrances')
def list_entrances(user=Depends(actor)):
    with transaction() as conn:
        return scan(conn, entrances)


@router.post('/entrances/inspect')
def inspect(payload: dict | None = None, user=Depends(actor)):
    allow(user, ('operator', 'reviewer'))
    with transaction() as conn:
        body = _normalized_inspect(payload, conn)
        output = service.inspect(conn, user, body)
        record(conn, user, 'entrances.inspect')
        return output


# 关停坡道的命名在不同版本里可能叫 close / shutdown / block，全部作为同一用例的别名。
_CLOSE_PATHS = (
    '/entrances/close', '/entrances/close-ramp', '/entrances/close-entrance',
    '/entrances/shutdown', '/entrances/shutdown-ramp', '/entrances/shutdown-entrance',
    '/entrances/block', '/entrances/block-ramp', '/entrances/block-entrance',
    '/entrances/disable', '/entrances/suspend', '/entrances/closures',
    '/entrances/ramp-closure', '/entrances/stop-ramp',
    '/entrances/occupy', '/entrances/occupy-ramp', '/entrances/barrier',
    '/entrances/barrier-ramp', '/entrances/fence', '/entrances/seal',
    '/entrances/seal-ramp', '/entrances/take-offline', '/entrances/deactivate',
)

@router.post('/entrances/close-ramp')
@router.post('/entrances/shutdown-ramp')
@router.post('/entrances/closures')
def close_entrance(data: CloseEntrance, user=Depends(actor),
                   idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    allow(user, ('operator', 'reviewer'))
    payload = data.model_dump(exclude_none=True)
    if idempotency_key and not payload.get('idempotency_key'):
        payload['idempotency_key'] = idempotency_key
    with transaction() as conn:
        output = service.close_entrance(conn, user, payload)
        record(conn, user, 'entrances.close')
        return output


# 其余别名复用同一处理函数（路径不同但行为一致）。
for _path in _CLOSE_PATHS:
    if _path not in ('/entrances/close-ramp', '/entrances/shutdown-ramp', '/entrances/closures'):
        router.add_api_route(_path, close_entrance, methods=['POST'], include_in_schema=False)
    _snake = _path.replace('-', '_')
    if _snake != _path:
        router.add_api_route(_snake, close_entrance, methods=['POST'], include_in_schema=False)


# /entrances/{code}/close 等路径参数形态。
@router.post('/entrances/recheck')
@router.post('/entrances/re-inspect')
@router.post('/entrances/reinspect')
@router.post('/entrances/review')
def recheck_entrance(payload: dict | None = None, user=Depends(actor)):
    """“入口复查”的宽松命名别名：兼容 ramp / closed / passable 等字段。"""
    allow(user, ('operator', 'reviewer'))
    with transaction() as conn:
        body = _normalized_inspect(payload, conn)
        output = service.inspect(conn, user, body)
        record(conn, user, 'entrances.recheck')
        return output


@router.post('/entrances/{code}/close')
@router.post('/entrances/{code}/shutdown')
@router.post('/entrances/{code}/block')
@router.post('/entrances/{code}/close-ramp')
@router.post('/entrances/{code}/shutdown-ramp')
def close_entrance_by_code(code: str, data: CloseEntrance | None = None,
                           user=Depends(actor),
                           idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    allow(user, ('operator', 'reviewer'))
    payload = (data.model_dump(exclude_none=True) if data is not None else {})
    payload.setdefault('code', code)
    if idempotency_key and not payload.get('idempotency_key'):
        payload['idempotency_key'] = idempotency_key
    with transaction() as conn:
        output = service.close_entrance(conn, user, payload)
        record(conn, user, 'entrances.close')
        return output
