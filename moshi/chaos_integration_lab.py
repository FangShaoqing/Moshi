"""Chaos Integration Lab · 混沌内芯 + 调制事件涌现 —— 接入 V3 的最小验证。

目标（与 16 方案一致）：
- 保留 V3 的世界反馈/事件涌现/波动性；
- 新增"混沌内芯"（Logistic，r≈3.9）调制事件强弱与偏向；
- 验证：混沌内芯/初始状态微扰 1e-9 → 轨迹距离是否显著放大（敏感依赖）。

运行：  python -m moshi.chaos_integration_lab
"""

from __future__ import annotations

import sys
import math
import random

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .v2.state import StateVector
from .v3 import world as W
from .v3.world import WorldState
from .v3.engine import EvolutionEngine, LifeStep


class ChaosEngine(EvolutionEngine):
    """V3 引擎 + 混沌内芯（Logistic）调制事件。"""

    def __init__(self, rng, **kw):
        super().__init__(rng, **kw)
        self.chaos_c = 0.4
        self.chaos_r = 3.9

    def run(self, state0, baseline, world) -> list[LifeStep]:
        S = state0
        steps = []
        for age in range(0, self.target_age + 1, self.step_years):
            # 混沌内芯先走一步（它是"命运进程"的敏感源）
            self.chaos_c = self.chaos_r * self.chaos_c * (1.0 - self.chaos_c)
            # 用混沌内芯调制"事件偏向"：c 高 → 偏主动/未来；c 低 → 偏防御/信任
            bias = self._chaos_bias()
            actives = self._active_domains_modulated(S, world, bias)
            delta = self._delta_from_world(S, world, actives)
            omega = self._omega()
            S_next = self._step(S, baseline, delta, omega)
            is_anchor = self._is_anchor(delta)
            steps.append(LifeStep(age=age, domains=actives, state=S, delta=delta,
                                  event_note=self._note(age, actives, delta), is_anchor=is_anchor))
            S = S_next
            world.step(self.rng)
        return steps

    def _chaos_bias(self) -> float:
        """混沌内芯值映射到 [-1,1]：c 高→+1（主动/向外），c 低→-1（防御/向内）。"""
        return self.chaos_c * 2.0 - 1.0

    def _active_domains_modulated(self, S, world, bias: float):
        scores = []
        for d in W.DOMAINS:
            invested = W.effective_investment(S, d)
            r = world.responses.get(d, 0.0)
            act = invested * abs(r)
            # 调制：bias>0 时，"未来/工作/表达自我"权重上升；bias<0 时，"信任/归属/亲密"权重上升
            if bias >= 0:
                if d in ("未来", "工作与生计", "表达自我"):
                    act *= (1.0 + 0.5 * bias)
            else:
                if d in ("信任", "归属", "亲密关系"):
                    act *= (1.0 + 0.5 * (-bias))
            scores.append((d, act))
        scores.sort(key=lambda x: x[1], reverse=True)
        top = [s for s in scores if s[1] > 0.05][:2]
        if not top:
            top = scores[:1]
        return top


def generate_chaos_person(seed: int, target_age: int = 30, chaos_c0: float | None = None) -> dict:
    rng = random.Random(seed)
    baseline = StateVector(
        valence=rng.uniform(0.35, 0.65), arousal=rng.uniform(0.30, 0.70),
        dominance=rng.uniform(0.30, 0.65), self_worth=rng.uniform(0.30, 0.60),
        trust=rng.uniform(0.30, 0.60), belonging=rng.uniform(0.30, 0.60),
    )
    s0 = StateVector(*[min(1.0, max(0.0, v + rng.uniform(-0.06, 0.06))) for v in baseline.as_list()])
    responses = {d: rng.uniform(-0.8, 0.8) for d in W.DOMAINS}
    world = WorldState(responses=responses)
    engine = ChaosEngine(rng=rng, target_age=target_age)
    if chaos_c0 is not None:
        engine.chaos_c = chaos_c0
    steps = engine.run(state0=s0, baseline=baseline, world=world)
    return {"seed": seed, "baseline": baseline, "state0": s0, "world": world,
            "steps": steps, "engine": engine}


def signature(result: dict) -> str:
    return "|".join(f"{st.age}:{','.join(f'{v:.4f}' for v in st.state.as_list())}" for st in result["steps"])


def main() -> None:
    print("=" * 66)
    print("  Chaos Integration Lab · 混沌内芯调制 —— 微扰是否被放大？")
    print("=" * 66)

    seed = 20260827
    r1 = generate_chaos_person(seed)
    r2 = generate_chaos_person(seed)
    print(f"\n【验证 1】同种子可复现？ {signature(r1) == signature(r2)}")

    # 验证 2：微扰混沌内芯初值 1e-9
    def rerun_with_pert(eps: float):
        r_a = generate_chaos_person(seed)
        r_b = generate_chaos_person(seed, chaos_c0=r_a["engine"].chaos_c + eps)
        # 注意：generate_chaos_person 的 engine 已跑完，直接取 r_a 与 r_b 的轨迹
        return r_a, r_b

    r_a, r_b = rerun_with_pert(1e-9)
    steps_a = r_a["steps"]
    steps_b = r_b["steps"]
    print(f"\n【验证 2】混沌内芯微扰 1e-9 → 轨迹分离情况")
    for a, b in zip(steps_a, steps_b):
        dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(a.state.as_list(), b.state.as_list())))
        print(f"  {a.age:>2}岁：距离 = {dist:.6f}" + ("  ← 显著分离" if dist > 0.02 else ""))
    final_dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(steps_a[-1].state.as_list(), steps_b[-1].state.as_list())))
    print(f"  → 微扰 1e-9 最终距离 {final_dist:.6f}（放大比 {final_dist/1e-9:.0f}x）")


if __name__ == "__main__":
    main()
