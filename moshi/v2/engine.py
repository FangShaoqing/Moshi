"""V2 生命引擎（engine）—— 线性演化动力学 + 完整闭环。

对应设计 15（线A）：
- 状态 S 是连续向量；演化方程：S_{t+1} = S_t + α·(P - S_t) + β·ΔS_t + ω_t
    α·(P-S)：惯性/向性情基线回归（成长公理）
    β·ΔS  ：事件脉冲（由状态与世界的交互算出，非"选"）
    ω     ：随机扰动（由种子 PRNG 注入，混沌的种子）
- 完整闭环：S →（行为 h(S)）→（情境交互 → 事件强度）→（ΔS 反哺）→ S_{t+1}

V2 = "分两步"的第一步：先线性（不期望真正混沌，只验证"演化+闭环"替换"选择+拼装"方向对不对）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from .state import StateVector, DIM_NAMES, make_state
from . import world as W


@dataclass
class LifeStep:
    """演化的一步：记录那一刻的状态与发生了的事。"""
    age: int
    domain: str
    state: StateVector
    delta: StateVector          # 事件脉冲 ΔS（这一步）
    event_note: str
    is_anchor: bool             # 是否为"锚点"（|ΔS| 大 = 显著弯曲点）


class EvolutionEngine:
    """线性演化引擎。S_{t+1} = S_t + α(P-S_t) + β·ΔS + ω。"""

    def __init__(self, rng: random.Random,
                 alpha: float = 0.03,      # 回归基线速率（惯性；小=慢，重大事件会更显著地"留痕"）
                 beta: float = 0.6,        # 事件脉冲增益（大=事件对状态的推动更强）
                 noise: float = 0.015,     # 随机扰动幅度
                 target_age: int = 30):
        self.rng = rng
        self.alpha = alpha
        self.beta = beta
        self.noise = noise
        self.target_age = target_age
        self.steps: list[LifeStep] = []

    # ── 主线：演化一生 ──
    def run(self, state0: StateVector, baseline: StateVector,
            event_plan: list[tuple[int, str]]) -> list[LifeStep]:
        """从 S0 出发，按 event_plan（[(年龄, 情境域), ...]）逐步演化到 target_age。

        event_plan 定义"她在这个年龄遇到哪个情境"——由先在条件 + 世界知识得出
        （V2 用简单规则：每个年龄一个情境；真实系统由状态与世界动态确定，此处先最小化）。
        """
        S = state0
        i = 0
        for age in range(0, self.target_age + 1, 5):
            # 找到这一站的情境（若事件计划里有；否则"平静"——无事件）
            domain = self._pick_domain(event_plan, age)

            delta = self._delta_from_event(S, domain) if domain else StateVector(*(0.0,)*6)
            omega = self._omega()

            S_next = self._step(S, baseline, delta, omega)
            is_anchor = self._is_anchor(delta)

            self.steps.append(LifeStep(age=age, domain=domain or "平静",
                                       state=S, delta=delta,
                                       event_note=self._note(domain, age, delta),
                                       is_anchor=is_anchor))
            S = S_next
        return self.steps

    # ── 动力学 ──
    def _step(self, S: StateVector, P: StateVector, delta: StateVector, omega: StateVector) -> StateVector:
        """S_{t+1} = S_t + α(P-S_t) + β·ΔS + ω，然后夹到 [0,1]。"""
        regress = S.diff(P).scale(-self.alpha)          # α(P-S)
        puls = delta.scale(self.beta)                    # β·ΔS
        nxt = S.add(regress).add(puls).add(omega)
        return nxt.clamp()

    def _delta_from_event(self, S: StateVector, domain: str) -> StateVector:
        """事件脉冲：由"状态 → 投入度 → 情境交互"算出（不是选标签）。"""
        invested = W.effective_investment(S, domain)
        intensity = W.event_intensity(S, domain, invested)
        return StateVector(*intensity)

    def _omega(self) -> StateVector:
        """随机扰动（混沌种子）。用 self.rng 保证同种子可复现。"""
        return StateVector(*(self.rng.uniform(-self.noise, self.noise) for _ in range(6)))

    def _pick_domain(self, plan: list[tuple[int, str]], age: int) -> str | None:
        """从事件计划里取这一站的 domain；无则 None（平静）。"""
        for a, d in plan:
            if a == age:
                return d
        return None

    @staticmethod
    def _is_anchor(delta: StateVector) -> bool:
        """锚点 = |ΔS| 显著大（这一步是"显著弯曲点"）。"""
        mag = max(abs(v) for v in delta.as_list())
        return mag >= 0.10

    @staticmethod
    def _note(domain: str, age: int, delta: StateVector) -> str:
        """把这一步"翻译"成一句人话（真实系统由大模型在合法格内填充；V2 规则生成）。"""
        if not domain:
            return f"{age}岁，一段平静的日子，没什么大事"
        top_dim = max(range(6), key=lambda i: abs(delta.as_list()[i]))
        dim_name = DIM_NAMES[top_dim]
        sign = "上升" if delta.as_list()[top_dim] > 0 else "下降"
        return f"{age}岁，在「{domain}」上经历了一件事，让她的「{dim_name}」{sign}"
