"""V1 生命引擎的"生成一个人"入口。

从种子（时代锚 + 随机数）→ 先在条件生发 → L2 推进器生成人生 → 陈默识（人格集合）。
输入：seed（整数，混沌的初始条件）。
输出：陈默识（Person，含水认识/倾向）+ 一段人生轨迹（steps）。
"""

from __future__ import annotations

import random
from typing import Any

from ..person import Person
from .engine import LifeEngine, generate_preconditions, Preconditions


def generate_person(seed: int, current_year: int = 2026, target_age: int = 30
                    ) -> tuple[Person, Preconditions, list[Any]]:
    """从一个种子生成"陈默识"。

    确定性：同 seed → 同一个 PRNG → 同一先在条件 → 同一段人生 → 同一个人。
    混沌：seed 一微扰，PRNG 序列全变，先在条件/事件链随之不同 → 不同人生。
    """
    rng = random.Random(seed)          # 用 seed 初始化确定性 PRNG
    pre = generate_preconditions(rng, current_year, target_min_age=max(5, target_age - 12),
                                 target_max_age=target_age)
    moshi = Person(name="陈默识")
    engine = LifeEngine(rng, current_year=current_year, target_age=target_age)
    steps = engine.run(moshi, pre)
    return moshi, pre, steps


def describe_life(pre: Preconditions, steps: list[Any]) -> str:
    """把"先在条件 + 人生轨迹"拼成一段人话（用于展示混沌差异）。"""
    lines = [f"先在条件：{pre.describe()}"]
    for s in steps:
        if s.event_domain == "信任":
            lines.append(f"  · {s.event_label}")
    return "\n".join(lines)
