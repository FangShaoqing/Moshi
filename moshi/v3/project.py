"""V3 认识投影器（project）—— 把"混沌轨迹"投影成"可读的人格"。

对应设计：
- 13/14：ΔS=丙（认识 + 强度）；Belief 是"从经历中涌现的非标签认识"。
- 15：认识 = 状态轨迹的"可读投影"，而非"从候选池选的标签"。

核心逻辑：
- 遍历 V3 轨迹的**锚点**（|ΔS| 大的显著弯曲点）；
- 每个锚点 → 一条 Belief：
  * cause       = 该步的事件叙事（真实经历）
  * domain      = 主情境域（受控词表）
  * tendency    = 由"该步状态净变化方向"决定的正/负倾向（非预设标签）
  * strength    = |ΔS| 大小（冲击越大认识越深）
  * attribution = 归因（从事件 + 状态变化人话生成）
  * tension     = 检测出"同领域但方向相反"的认识 → 矛盾并存（厚度/优秀线）

注意：这里 tendency 目前用"简单规则映射"（领域×净方向），真实系统应由大模型在受控 domain 下填充质感（结构归算法、质感归大模型）。
"""

from __future__ import annotations

from typing import Any

from ..v0.belief import Belief
from ..v2.state import DIM_NAMES
from . import world as W

_DOMAIN_COEFF_REF = W.DOMAIN_COEFF   # 领域系数（方向判定用，与引擎 _note 同源）


# ── 受控的"倾向"映射：领域 × 方向(正/负) → 可读的倾向表述（结构部分，算法定）──
# 【甲方向：每条认识自带张力】表述本身是矛盾的（深层纠缠），
# 而非"一条倾向 + 一条相反倾向配对"。真实人性：想靠近又怕受伤，常在同一条认识里。
TENDENCY_MAP: dict[str, dict[str, list[str]]] = {
    "信任": {
        "up": ["渴望相信人，却又总会留一手，怕再一次错付",
               "想放下戒备，可一想起过去的事，又悄悄把门关上了"],
        "down": ["把信任当稀缺品，其实心里盼着有人值得她交出去",
                 "不敢全盘托付——不是不想要，是怕再伤一次"],
    },
    "亲密关系": {
        "up": ["想靠近一个人，又总是怕靠自己太近会伤到自己",
               "羡慕别人敢爱，轮到她自己，脚却钉在原地"],
        "down": ["靠近了又想逃，逃开了又后悔，心里始终有一个想被接住的位置",
                 "她把距离当安全，可其实一直在等一个不让她逃的人"],
    },
    "工作与生计": {
        "up": ["想安稳，又嫌安稳太闷；想闯，又怕闯不起",
               "一边说服自己接受平凡，一边还没死心"],
        "down": ["把活着放在理想前面，但那股没熄的念头偶尔还是会痒",
                 "她认了命，却又不甘心认命"],
    },
    "金钱": {
        "up": ["想靠钱买到踏实，可钱多了心里还是空的",
               "会精打细算留后路，但偶尔也想为自己挥霍一次"],
        "down": ["对钱敏感怕吃亏，可真算得太清又觉得自己凉薄",
                 "嘴上说够花就行，心里其实怕哪天不够花"],
    },
    "自我价值": {
        "up": ["开始相信自己值得，却又总在重要时刻怀疑自己",
               "学会不拿别人标准衡量自己，可还是习惯先看别人脸色"],
        "down": ["总觉得自己不配，可内心又有个声音说'其实你也可以'",
                 "习惯否定自己，却一直悄悄盼着有人看见她"],
    },
    "归属": {
        "up": ["想把一处当家守住，又怕这'家'突然不要她了",
               "对接纳她的人依赖，却克制着，怕一靠近就失去"],
        "down": ["觉得自己在哪个圈子都像外人，但到底还是想被留下",
                 "习惯了独处，可有时还是会被热闹晃了一下神"],
    },
    "未来": {
        "up": ["想把'以后'握在自己手里，又怕握得太用力反而攥丢了",
               "敢去够那个念头，却总在半路回头看看退路"],
        "down": ["把理想和活下去分开，但理想没真的死",
                 "不敢想太远，其实是怕想了又落空"],
    },
    "表达自我": {
        "up": ["想说出心里话，可话到嘴边又怕说出来没人接",
               "学会了说'我需要''我不想'，但说完还是忐忑"],
        "down": ["把话咽了回去，咽完又有点不甘——其实她一直想被听见",
                 "藏得很深，最深处却藏着'要是有人懂我该多好'"],
    },
}

# 领域 → 归因短语（用于 attribution 的人话；领域语义比维度更贴切）
DOMAIN_ATTR: dict[str, str] = {
    "信任": "她对'谁能信'这件事的看法变了",
    "亲密关系": "她对'亲密'和'距离'的感受变了",
    "工作与生计": "她对'生计'和'安稳'的理解变了",
    "金钱": "她对'钱'和'安稳'的分量变了",
    "自我价值": "她对自己'配不配'的看法变了",
    "归属": "她对'家'和'被接纳'的感觉变了",
    "未来": "她对'以后'的期待变了",
    "表达自我": "她对'敢不敢说出口'的底气变了",
}

# ── 人性张力原型（深层纠缠）──
# 每条张力 = "两端"，每端用 (领域, 方向) 表达。当两条认识分别落在同一弧的两端时，
# 它们之间存在**深层张力**（跨领域、语义纠缠），如"渴望被爱"vs"害怕受伤"。
# 这不是"同领域一正一反"的浅层矛盾，而是人性真正的复杂性。
TENSION_ARCS: list[dict] = [
    {
        "name": "靠近与退缩",
        "ends": [("亲密关系", "up"), ("信任", "down")],
        "desc": "她渴望有人靠近，又本能地防御——爱和怕伤是同一件事的两面",
    },
    {
        "name": "想要家与习惯独处",
        "ends": [("归属", "up"), ("归属", "down")],
        "desc": "她想要一个家，却已经习惯了独自一人",
    },
    {
        "name": "自强与依赖",
        "ends": [("工作与生计", "up"), ("金钱", "up"), ("归属", "down")],
        "desc": "她什么都想靠自己，却又盼望有人接住",
    },
    {
        "name": "敢说与怕被听见",
        "ends": [("表达自我", "up"), ("表达自我", "down")],
        "desc": "她渴望被听见，又怕开口就是错",
    },
    {
        "name": "值得与不配",
        "ends": [("自我价值", "up"), ("自我价值", "down")],
        "desc": "她一边相信值得，一边觉得自己不配",
    },
    {
        "name": "理想与现实",
        "ends": [("未来", "up"), ("未来", "down")],
        "desc": "她心里有没熄的念头，却得先低头活下去",
    },
]


def find_tension(belief_a: Belief, belief_b: Belief) -> str | None:
    """判断两条认识是否落在同一条张力弧的两端；是则返回弧的 desc。"""
    key_a = (belief_a.domain, "up" if belief_a.tendency in TENDENCY_MAP.get(
        belief_a.domain, {}).get("up", []) else "down")
    key_b = (belief_b.domain, "up" if belief_b.tendency in TENDENCY_MAP.get(
        belief_b.domain, {}).get("up", []) else "down")
    for arc in TENSION_ARCS:
        ends = set(tuple(e) for e in arc["ends"])
        # 两条认识分别落在弧的两端（不同端）
        if key_a in ends and key_b in ends and key_a != key_b:
            return arc["desc"]
    return None


def _net_direction(state_vals: list[float], prev_vals: list[float] | None,
                   dim_idx: int | None) -> str:
    """由净变化方向（若有 prev）或当前维度高低给出 'up'/'down'。"""
    if prev_vals is not None and dim_idx is not None:
        d = state_vals[dim_idx] - prev_vals[dim_idx]
        return "up" if d >= 0 else "down"
    return "up"


def project_beliefs(result: dict[str, Any], max_steps: int = 15) -> list[Belief]:
    """从轨迹投影出"认识"——**累积固化**机制（修复"小事也长成大人执念"的巨婴问题）。

    真实人性的形成：**单次小事件不改变人**；只有"单次重大事件"或"同方向反复累积"才会
    固化一条认识。这里：
    - 按 (领域, 方向) 聚合整个一生的冲击量（sum |ΔS| 中该领域的贡献）；
    - 聚合量达到阈值（累积固化线）→ 固化一条认识；
    - 认识强度 ∝ 累积量（"开始"→"渐渐"→"已经"）；
    - 同领域 up/down 都达标则并存（厚度，tension 标注）。
    """
    steps = result["steps"]
    # (domain, direction) -> accumulated impact
    accum: dict[tuple[str, str], float] = {}
    # (domain, direction) -> (触发事件, 年龄)
    trigger: dict[tuple[str, str], tuple[str, int]] = {}

    for st in steps:
        if not st.domains:
            continue
        domain = st.domains[0][0]
        if domain not in TENDENCY_MAP:
            continue
        # 方向判定改进：用"该领域自身事件方向"（与引擎 _note 同源：世界响应 r × 该领域代表性维度系数），
        # 而非 delta 净方向——避免多领域对冲导致"叙事说咽回去、倾向却是正面"的方向错位。
        r_main = result["world"].responses.get(domain, 0.0)
        coeff = _DOMAIN_COEFF_REF.get(domain, (0.0,) * 6)
        rep_idx = max(range(len(coeff)), key=lambda i: abs(coeff[i]))
        direction = "up" if (r_main * coeff[rep_idx]) >= 0.0 else "down"
        key = (domain, direction)
        # 累计该方向冲击量；同时把冲击最大的那次作为"触发事件"
        delta = st.delta.as_list()
        dim_idx = max(range(len(delta)), key=lambda i: abs(delta[i])) if any(delta) else None
        hit = abs(delta[dim_idx]) if dim_idx is not None else 0.0
        accum[key] = accum.get(key, 0.0) + hit
        if key not in trigger or hit > trigger[key][0]:
            trigger[key] = (hit, st.event_note, st.age)

    # 固化：累积量超过阈值 → 一条认识（**成熟化**：只有足够分量的经历才固化，日常不进入）
    CUMULATE_THRESHOLD = 0.14      # 提高：单次小事件(≈0.01~0.03)或少量日常积累(≈0.05~0.1)不达标；
                                   # 只有"重大事件（重尾）或同方向反复重大累积"才固化 → 认识少而深
    beliefs: list[Belief] = []
    used_ids = 0
    for (domain, direction), amount in sorted(accum.items(), key=lambda kv: -kv[1]):
        if amount < CUMULATE_THRESHOLD:
            continue
        if len(beliefs) >= 5:      # 认识上限：少而深（最多 5 条，只保留分量最大的）
            break
        hit, cause, age = trigger[(domain, direction)]   # 触发事件（冲击最大的那次）
        # 倾向（结构性：领域×方向）
        candidates = TENDENCY_MAP[domain]["up" if direction == "up" else "down"]
        tendency = candidates[used_ids % len(candidates)]
        # 强度 ∝ 累积量（0.35~0.92，不饱和）
        strength = max(0.35, min(0.92, 0.35 + amount * 1.2))
        # 归因（按领域）
        attr = f"经历了这样的事，{DOMAIN_ATTR.get(domain, '整个人')}，她慢慢长出了这个倾向"
        beliefs.append(Belief(
            id=f"proj::{used_ids}",
            cause=cause,
            domain=domain,
            tendency=tendency,
            attribution=attr,
            strength=strength,
            salience=0.5,
            formed_at=age,
        ))
        used_ids += 1
        if len(beliefs) >= max_steps:
            break

    # tension：命中"人性张力弧"（跨领域深层纠缠）→ 标矛盾；
    # 同时保留"同领域正反"的简单形式作为兜底（若没命中弧但方向相反，仍算内部张力）。
    for a in beliefs:
        for b in beliefs:
            if a is b:
                continue
            arc = find_tension(a, b)
            if arc:
                a.tension.append(f"[{arc}]")
            elif a.domain == b.domain:
                a_up = a.tendency in TENDENCY_MAP.get(a.domain, {}).get("up", [])
                b_up = b.tendency in TENDENCY_MAP.get(b.domain, {}).get("up", [])
                if a_up != b_up:
                    a.tension.append("同领域内反复拉扯")
    return beliefs


def summarize(person: list[Belief]) -> str:
    """把人（认识集合）压缩成一句人类可读的概括。"""
    if not person:
        return "（这个宇宙里没有显著的锚点认识）"
    lines = [f"她长出了 {len(person)} 条认识："]
    for b in person:
        lines.append(f"  · {b.as_condition()}")
    return "\n".join(lines)
