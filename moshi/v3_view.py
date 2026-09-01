"""V3 · 过程可视化 —— 把"演化过程"展示出来，而不是"一份报告"。

目标：让用户能"看见"她是怎么一步步长大的：
- 每"步"（年龄）显示：
  * 她的 6 维状态（用色块柱状图 —— █ 表示强度）
  * 世界运势（当前各领域的顺/逆风）
  * 切到的具体事件（叙事）
- 这样"过程感"就出来了：状态在移动、世界在起伏、事件在发生。

运行（作为 v3_demo 的展示部分）：  python -m moshi.v3_view
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .v3.generate import generate_person
from .v2.state import DIM_NAMES

# 中文维度名（展示层用）
CN_DIMS: dict[str, str] = {
    "Valence": "愉悦", "Arousal": "活力", "Dominance": "主导",
    "SelfWorth": "自我", "Trust": "信任", "Belonging": "归属",
}

# 维度变化 → 人话
def dim_phrase(dim: str, delta: float) -> str:
    up = delta > 0
    if dim == "Valence":
        return "她感觉更好了" if up else "她更沮丧了"
    if dim == "Arousal":
        return "她更有劲了" if up else "她更疲惫了"
    if dim == "Dominance":
        return "她更有掌控感" if up else "她更无力了"
    if dim == "SelfWorth":
        return "她更相信自己了" if up else "她更怀疑自己了"
    if dim == "Trust":
        return "她更愿意相信别人" if up else "她更难相信别人了"
    if dim == "Belonging":
        return "她更有归属感" if up else "她更觉得飘着"
    return dim


# ── 终端可视化工具 ──

def bar(value: float, width: int = 22) -> str:
    """把 [0,1] 值画成色块条：█ 越多越强。"""
    filled = int(round(max(0.0, min(1.0, value)) * width))
    return "█" * filled + "░" * (width - filled)


def show_timeline(result: dict, title: str) -> None:
    """逐步展示"她的一生"：每一步 → 状态柱状 + 事件叙事。"""
    print(f"\n{'=' * 78}")
    print(f"  {title}")
    print(f"{'=' * 78}")
    print("世界运势（顺风 →/ 逆风 ←）：")
    print("  " + "  ".join(f"{d}{'→' if r >= 0 else '←'}{abs(r):.1f}"
                          for d, r in result["world"].responses.items()))
    print(f"\n基线与初始状态：")
    print(f"  基线P：{result['baseline'].describe()}")
    print(f"  初始S0：{result['state0'].describe()}")
    print()

    # 表头
    print(f"{'年龄':<4} | {'她此刻的样子（6维，█=强，中文）':<80}")
    print(f"{'-'*4}-+-{'-'*80}")

    prev = None
    for st in result["steps"]:
        # 状态柱状图（中文维度名）
        vals = st.state.as_list()
        bars = "  ".join(f"{CN_DIMS.get(n, n)}:{bar(v):18}" for n, v in zip(DIM_NAMES, vals))
        marker = " ★锚点" if st.is_anchor else ""
        print(f"{st.age:>3}岁 | {bars}")
        # 事件叙事
        print(f"{'':4} |   ↳ {st.event_note}{marker}")
        # 状态变化（人话）
        if prev is not None:
            changes = []
            for n, a, b in zip(DIM_NAMES, prev, vals):
                d = b - a
                if abs(d) >= 0.02:
                    changes.append(f"{dim_phrase(n, d)}（{CN_DIMS.get(n, n)} {d:+.2f}）")
            if changes:
                print(f"{'':4} |     这段经历后：{'；'.join(changes)}")
        prev = vals
        print()


def show_chaos_verification(seed: int) -> None:
    """把"混沌敏感验证"以过程图展示（两种微扰轨迹的分离）。"""
    from .v3.engine import EvolutionEngine
    from .v3.world import WorldState
    import random, math

    r1 = generate_person(seed)

    def build(c0: float):
        rng = random.Random(seed)
        world = WorldState(responses=dict(r1["world"].responses))
        eng = EvolutionEngine(rng=rng, chaos_c0=c0, target_age=r1["target_age"])
        return eng.run(state0=r1["state0"], baseline=r1["baseline"], world=world)

    stepsA = build(0.4)
    stepsB = build(0.4 + 1e-9)

    print(f"{'=' * 78}")
    print(f"  混沌敏感验证：混沌内芯微扰 1e-9 → 轨迹分离（过程图）")
    print(f"{'=' * 78}")
    print(f"{'年龄':<4} | {'轨迹距离（两个版本的差异）':<30}")
    print(f"{'-'*4}-+-{'-'*30}")
    for a, b in zip(stepsA, stepsB):
        dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(a.state.as_list(), b.state.as_list())))
        # 用柱状展示距离的相对大小（方便肉眼看见分离）
        width = int(dist * 300)
        print(f"{a.age:>3}岁 | {dist:.6f}  {'█' * min(width, 40)}" + ("  ★分离" if dist > 0.02 else ""))
    final = math.sqrt(sum((x - y) ** 2 for x, y in zip(stepsA[-1].state.as_list(), stepsB[-1].state.as_list())))
    print(f"\n→ 微扰 1e-9，最终距离 {final:.6f}（放大比 {final/1e-9:.0f}x）")


def main() -> None:
    seed = 20260827
    r1 = generate_person(seed)
    r2 = generate_person(seed)

    print(f"\n【确定性】同种子({seed}) → 轨迹签名相等？ {__import__('moshi.v3.generate', fromlist=['trajectory_signature']).trajectory_signature(r1) == __import__('moshi.v3.generate', fromlist=['trajectory_signature']).trajectory_signature(r2)}")

    show_timeline(r1, f"陈默识 · 一生 · 过程视图（seed={seed}）")
    show_chaos_verification(seed)


if __name__ == "__main__":
    main()
