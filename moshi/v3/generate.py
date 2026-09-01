"""V3 生成入口：种子 → 出生日期/世界状态/性情基线/初始状态 → 演化 → 人生轨迹。

关键（本次需求）：
- **出生日期**：在 [2000-01-01, 2006-12-31] 之间随机选取（具体日期，非仅年份）。
- **年龄 = 当前日期 - 出生日期**（"当下"的年龄；不再是固定的 30 岁）。
  那"现在"是哪一天？用现实当前日期（time.time()）——她活在现实时间中，
  交于"当下"时，她的年龄自然地由日期差决定。
"""

from __future__ import annotations

import datetime
import random
from typing import Any

from ..v2.state import StateVector
from .engine import EvolutionEngine
from . import world as W

# 出生日期区间（需求指定）
BIRTH_RANGE_START = datetime.date(2000, 1, 1)
BIRTH_RANGE_END = datetime.date(2006, 12, 31)


def _random_birth_date(rng: random.Random) -> datetime.date:
    """在 [2000-01-01, 2006-12-31] 内随机选一个具体日期（含端点）。"""
    start_ord = BIRTH_RANGE_START.toordinal()
    end_ord = BIRTH_RANGE_END.toordinal()
    return datetime.date.fromordinal(rng.randint(start_ord, end_ord))


def age_on(birth: datetime.date, on: datetime.date | None = None) -> int:
    """在某一天（默认今天=现实"当下"）她几岁（周岁）。"""
    on = on or datetime.date.today()
    years = on.year - birth.year
    # 还没到今年生日则减一（周岁）
    if (on.month, on.day) < (birth.month, birth.day):
        years -= 1
    return max(0, years)


def generate_person(seed: int, now: datetime.date | None = None) -> dict[str, Any]:
    """从种子"演化"出陈默识 + 她所在的世界。

    - 出生日期：由种子在 [2000-01-01, 2006-12-31] 内随机选取。
    - 年龄：由"当下"（now，默认今天）推导 —— 她活在当下，不是固定的 30 岁。
    - 人生演化到她的年龄为止（每 3 年一步）。
    """
    now = now or datetime.date.today()
    rng = random.Random(seed)

    # ① 出生日期（具体日期，由种子决定）
    birth_date = _random_birth_date(rng)
    current_age = age_on(birth_date, now)

    # ② 性情基线 P（先天性情）
    baseline = StateVector(
        valence=rng.uniform(0.35, 0.65),
        arousal=rng.uniform(0.30, 0.70),
        dominance=rng.uniform(0.30, 0.65),
        self_worth=rng.uniform(0.30, 0.60),
        trust=rng.uniform(0.30, 0.60),
        belonging=rng.uniform(0.30, 0.60),
    )

    # ③ 初始 S0（在 P 附近小幅偏离 = 混沌的"初始条件"）
    s0 = StateVector(
        *[min(1.0, max(0.0, v + rng.uniform(-0.06, 0.06))) for v in baseline.as_list()]
    )

    # ④ 世界状态：每个情境的世界响应基线（顺/逆风），由种子初始化 → 种子决定"世界运势"
    responses = {d: rng.uniform(-0.8, 0.8) for d in W.DOMAINS}
    world = W.WorldState(responses=responses)

    # ⑤ 事实库（硬事实：家庭/求学/工作/身份）—— 与演化同一 rng，先于演化生成（确定性）。
    #    由种子选家庭阶层/氛围（与 V3 先在条件同风格），作为"她是谁"的静态锚点。
    from ..v4.facts import generate_facts
    fam_class = rng.choice(["贫困", "普通", "小康", "富足"])
    fam_atm = rng.choice(["温暖", "冷淡", "紧张", "动荡"])
    facts = generate_facts(rng, birth_date, family_class=fam_class,
                           family_atmosphere=fam_atm, current_age=current_age)

    # ⑥ 演化（事件涌现，非预排）——演到"当下年龄"为止；V5：传入家庭阶层（同源叙事）
    engine = EvolutionEngine(rng=rng, target_age=current_age, family_class=facts.family_class)
    steps = engine.run(state0=s0, baseline=baseline, world=world)

    # ⑦ 每个时间点补上"具体年份"（出生日期 + 年龄 → 真实日历年份）
    for st in steps:
        st.year = birth_date.year + st.age
        # 若当年生日未到（年龄跨越），年份可能 +1；简化为"出生年 + 年龄"（够用够真）

    return {"seed": seed, "birth_date": birth_date, "current_age": current_age,
            "now": now, "baseline": baseline, "state0": s0,
            "world": world, "steps": steps, "target_age": current_age,
            "facts": facts}


def trajectory_signature(result: dict[str, Any]) -> str:
    parts = []
    for st in result["steps"]:
        parts.append(f"{st.age}:{','.join(f'{v:.4f}' for v in st.state.as_list())}")
    return "|".join(parts)
