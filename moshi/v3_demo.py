"""V3 · 演示 —— 非线性混沌演化内核（世界反馈 + 非线性 + 事件涌现）。

验证四项：
  1. 确定性：同种子 → 同一轨迹（可复现）。
  2. 混沌敏感：初始 S0 微扰 ±ε → 轨迹分离（非线性放大的直接证据）。
  3. 波动性：状态不再单向上涨，而是像人生一样起伏（世界反馈生效）。
  4. 事件涌现：不同种子 → 出现不同的"发生什么事"序列（非预排）。

运行：  python -m moshi.v3_demo
"""

from __future__ import annotations

import sys
import math

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .v3.generate import generate_person, trajectory_signature
from .v2.state import StateVector, DIM_NAMES


def show(result: dict, title: str) -> None:
    print(f"\n───── {title} ─────")
    print(f"基线 P：{result['baseline'].describe()}")
    print(f"S0    ：{result['state0'].describe()}")
    print(f"世界运势：{ {d: round(r, 2) for d, r in result['world'].responses.items()} }")
    for st in result["steps"]:
        mk = "  ← 锚点" if st.is_anchor else ""
        print(f"  {st.age:>2}岁  {st.event_note}{mk}")
        print(f"        S={st.state.describe()}")


def main() -> None:
    print("=" * 66)
    print("  Moshi V3 · 非线性混沌演化内核 —— 世界反馈 + 非线性 + 事件涌现")
    print("=" * 66)

    seed = 20260827
    r1 = generate_person(seed)
    r2 = generate_person(seed)

    print(f"\n【验证 1】确定性：同种子({seed}) → 轨迹签名相等？ {trajectory_signature(r1) == trajectory_signature(r2)}")
    show(r1, "陈默识 · 一生（seed={0}）".format(seed))

    # 验证 2：混沌敏感 —— 微扰"混沌内芯"初值 1e-9（混沌源是内芯，不是外部噪声）
    print("\n【验证 2】混沌敏感：混沌内芯微扰 1e-9 → 轨迹分离情况")
    from .v3.engine import EvolutionEngine
    from .v3.world import WorldState
    import random

    def rerun_with_core_eps(eps: float):
        """同种子、同世界，仅混沌内芯初值差 eps。"""
        def build(c0: float):
            rng = random.Random(seed)
            baseline = r1["baseline"]
            s0 = r1["state0"]
            world = WorldState(responses=dict(r1["world"].responses))
            # 与 generate_person 一致：用她"当下"的年龄作为演化长度
            eng = EvolutionEngine(rng=rng, chaos_c0=c0, target_age=r1["target_age"])
            steps = eng.run(state0=s0, baseline=baseline, world=world)
            return steps
        return build(0.4), build(0.4 + eps)

    stepsA, stepsB = rerun_with_core_eps(1e-9)
    for a, b in zip(stepsA, stepsB):
        dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(a.state.as_list(), b.state.as_list())))
        print(f"  {a.age:>2}岁：轨迹距离 = {dist:.6f}" + ("  ← 显著分离" if dist > 0.02 else ""))
    final_dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(stepsA[-1].state.as_list(), stepsB[-1].state.as_list())))
    print(f"  → 初始微扰 1e-9，最终距离 {final_dist:.6f}（放大比 {final_dist/1e-9:.0f}x）")

    # 验证 3：波动性 —— 状态是否起伏（不是单调）
    states = [st.state.as_list() for st in r1["steps"]]
    waved = False
    for dim in range(6):
        seq = [s[dim] for s in states]
        ups = sum(1 for i in range(1, len(seq)) if seq[i] > seq[i - 1])
        downs = sum(1 for i in range(1, len(seq)) if seq[i] < seq[i - 1])
        if ups > 0 and downs > 0:
            waved = True
    print(f"\n【验证 3】波动性（存在先升后降/先降后升的维度）？ {waved}")

    # 验证 4：事件涌现 —— 不同种子 → 不同事件序列
    r_other = generate_person(seed + 1)
    seq1 = [(st.age, "、".join(d for d, _ in st.domains)) for st in r1["steps"]]
    seq2 = [(st.age, "、".join(d for d, _ in st.domains)) for st in r_other["steps"]]
    print(f"\n【验证 4】事件涌现：种子 +1 的事件序列是否不同？ {seq1 != seq2}")
    print("  种子    :", [f"{a}:{d}" for a, d in seq1])
    print("  种子+1  :", [f"{a}:{d}" for a, d in seq2])


if __name__ == "__main__":
    main()
