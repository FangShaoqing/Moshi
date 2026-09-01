"""V2 生成入口：种子 → 性情基线/初始状态/事件计划 → 演化出轨迹。

关键（对比 V1）：
- 先在条件由系统生发（仍在合法空间：基线 P 从候选中按种子抽样、事件计划按种子排序），
  但**不再直接给出"认识标签"** —— 人格来自状态演化，认识是轨迹上的"可读投影"（V2 暂用 note 展示）。
"""

from __future__ import annotations

import random
from typing import Any

from .state import StateVector, DIM_NAMES
from .engine import EvolutionEngine, LifeStep
from . import world as W


# ── 先在条件（V2：仍由系统生发，但只给出"情境计划"与基线偏移）──

EVENT_DOMAINS = list(W.SITUATIONS.keys())   # 世界情境域（不是"认识标签池"）


def generate_person(seed: int, target_age: int = 30) -> dict[str, Any]:
    """从一个种子"演化"出陈默识。

    输入 seed 决定：性情基线 P、初始 S0、以及"她在哪些年龄遇到哪些情境"(事件计划)。
    输出：dict {baseline, state0, steps, person_summary}
    """
    rng = random.Random(seed)

    # ① 性情基线 P：由种子在合法范围内抽样（V2：直接用连续抽样，代表"先天性情"）
    baseline = StateVector(
        valence=rng.uniform(0.35, 0.65),
        arousal=rng.uniform(0.30, 0.70),
        dominance=rng.uniform(0.30, 0.65),
        self_worth=rng.uniform(0.30, 0.60),
        trust=rng.uniform(0.30, 0.60),
        belonging=rng.uniform(0.30, 0.60),
    )

    # ② 初始 S0：从 P 附近出发（小幅偏离，混沌的"初始条件"）
    s0 = StateVector(
        *[min(1.0, max(0.0, v + rng.uniform(-0.06, 0.06))) for v in baseline.as_list()]
    )

    # ③ 事件计划：每个 5 岁采样点分配一个情境（V2 简化为：种子决定先后顺序）
    ages = list(range(5, target_age + 1, 5))
    plan: list[tuple[int, str]] = []
    for age in ages:
        domain = rng.choice(EVENT_DOMAINS)
        plan.append((age, domain))

    # ④ 演化
    engine = EvolutionEngine(rng=rng, target_age=target_age)
    steps = engine.run(state0=s0, baseline=baseline, event_plan=plan)

    return {
        "seed": seed,
        "baseline": baseline,
        "state0": s0,
        "steps": steps,
        "target_age": target_age,
    }


def trajectory_signature(result: dict[str, Any]) -> str:
    """轨迹签名：用于"同种子可复现"验证（含每步状态）。"""
    parts = []
    for st in result["steps"]:
        parts.append(f"{st.age}:{st.domain}:{','.join(f'{v:.4f}' for v in st.state.as_list())}")
    return "|".join(parts)
