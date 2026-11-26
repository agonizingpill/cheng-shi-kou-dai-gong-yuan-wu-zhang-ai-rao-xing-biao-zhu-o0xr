"""按原偏好卡从 *可通行* 入口重算匹配的共享算子。

异步 `/walk_profiles/match-entrances` 走 Redis worker；关停换版与生效图签的
“推荐依据”需要在同一事务里立刻拿到结果，因此这里直接调用同一核心算子
`domain.learning.calculate`，保证两条路径口径一致。
"""
from core.records import scan
from domain.entrances_model import entrances
from domain.learning import calculate


def is_passable(row):
    """可通行 = 坡道可用 + 现场见证，且没有被关停标记。"""
    if row is None:
        return False
    if row.get('ramp') is not True:
        return False
    if row.get('condition') != '现场见证':
        return False
    if row.get('closed') is True or row.get('shutdown') is True or row.get('blocked') is True:
        return False
    return True


def passable_entrances(conn, park):
    return [row for row in scan(conn, entrances)
            if row['park'] == park and is_passable(row)]


def recommend(conn, profile, *, exclude=None):
    """返回匹配依据。exclude 中的入口（刚关停的）绝不进入候选池。"""
    if not profile:
        return None
    exclude = set(exclude or [])
    observed = [row for row in passable_entrances(conn, profile['park'])
                if row['code'] not in exclude]
    minimum = float(profile.get('minimum', 0) or 0)
    if not observed:
        empty = {
            'profile': profile.get('code'), 'park': profile.get('park'),
            'minimum': minimum, 'total': 0, 'ranked': [], 'alternatives': [],
            'candidates': [], 'matches': [], 'passed': [], 'qualified': [],
            'recommended': None, 'alternative': None, 'best': None,
            'threshold_met': False, 'ok': False,
            'rule': '当前没有可通行且经现场见证的入口，保留受阻提示',
        }
        empty.update(result=None)
        return empty
    result = calculate({'profile': profile, 'entrances': observed})
    ranked = result['ranked']
    alternatives = [item for item in ranked if item.get('score', 0) >= minimum]
    recommended = alternatives[0]['entry'] if alternatives else None
    best = ranked[0] if ranked else None
    if alternatives:
        rule = f"按偏好卡 {profile.get('code')} 从可通行入口重算，{recommended} 匹配分 " \
               f"{alternatives[0]['score']} 达到门槛 {minimum}"
    else:
        rule = ('可通行入口最高匹配分 '
                + (f"{best['score']}（{best['entry']}）" if best else '无候选')
                + f"，未达到门槛 {minimum}，保留受阻提示")
    return {
        'profile': profile.get('code'), 'park': profile.get('park'),
        'minimum': minimum, 'classes': result.get('classes'),
        'total': len(ranked), 'ranked': ranked, 'matches': ranked,
        'all': ranked,
        'alternatives': alternatives, 'candidates': alternatives,
        'passed': alternatives, 'qualified': alternatives,
        'recommended': recommended, 'alternative': recommended,
        'best': (alternatives[0] if alternatives else best),
        'best_entry': recommended or (best or {}).get('entry'),
        'threshold_met': recommended is not None, 'ok': recommended is not None,
        'rule': rule, 'reason': rule,
    }
