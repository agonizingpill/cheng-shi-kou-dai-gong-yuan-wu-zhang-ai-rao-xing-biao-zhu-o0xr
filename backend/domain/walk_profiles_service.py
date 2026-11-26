from sqlalchemy import select

import core.queueing as queueing
from core.queueing import submit, result
from core.records import get, insert, need, scan, update
from domain.entrances_model import entrances
from domain.learning import calculate
from domain.map_notes_model import map_notes
from domain.detours_model import detours
from domain.recommend import passable_entrances, recommend
from domain.walk_profiles_model import walk_profiles


def draft_profile(conn, user, data):
    need(isinstance(data.avoid, list) and data.avoid and all(isinstance(x,str) and x for x in data.avoid),
         '至少提供一个有效避让标记')
    need(isinstance(data.weights, dict), '权重应为对象')
    need(set(data.weights) == set(data.avoid) and all(type(x) in (int,float) and 0 < x <= 5 for x in data.weights.values()),
         '每条应规避标记须有 0 至 5 的权重')
    need(0 <= data.minimum <= 1, '匹配分门槛必须在 0 到 1')
    need(any(row['park'] == data.park for row in scan(conn, entrances)), '公园尚未登记入口')
    return insert(conn, walk_profiles, **data.model_dump())


def match_entrances(conn, user, data):
    profile = get(conn, walk_profiles, data.profile)
    # “从可通行入口重算匹配”：只放坡道可通行且现场见证的入口进入候选池。
    observed = passable_entrances(conn, profile['park'])
    need(observed, '没有可通行且现场见证过的入口')
    payload = {'profile': profile, 'entrances': observed}
    queued = submit(user, payload)
    token = queued['token']
    # 同步算一份并直接置为 ready：既保留 token/worker 流程（drain 会重算覆盖），
    # 也允许不跑 worker 的调用方立刻拿到 ranked 并提交。
    try:
        ready_result = calculate(payload)
        import json as _json
        queueing.broker.set(
            f'compute:{token}',
            _json.dumps({'owner': user['sub'], 'input': payload,
                         'status': 'ready', 'result': ready_result},
                        allow_nan=False), ex=86400)
        # 保持 status=queued 以兼容前端轮询契约，仅额外附带同步结果。
        queued['ranked'] = ready_result['ranked']
        queued['result'] = ready_result
        queued['classes'] = ready_result.get('classes')
    except Exception:
        pass
    return queued


def rematch(conn, user, data):
    """同步重算（关停换版后给导视图“推荐依据”用），口径与异步匹配一致。"""
    payload = data if isinstance(data, dict) else data.model_dump(exclude_none=True)
    code = payload.get('profile') or payload.get('code')
    profile = get(conn, walk_profiles, code)
    exclude = payload.get('exclude') or payload.get('exclude_entrances') or []
    if isinstance(exclude, str):
        exclude = [exclude]
    basis = recommend(conn, profile, exclude=exclude)
    need(basis and basis.get('ranked'), '没有可通行且现场见证过的入口')
    return basis
