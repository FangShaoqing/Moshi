"""V2 · 演示 —— 线性演化内核：状态真的在"移动"，而非"选择拼装"。

要点（对比 V1）：
- 状态 S 是 6 维连续向量，每个时刻都在"演化"（方程变换），不是"追加条目"。
- 事件强度由"状态 × 世界情境"交互计算（闭环），不是从候选池"选"。
- 验证：同种子 → 同一轨迹（可复现）；锚点 = |ΔS| 大的显著弯曲点。

运行：  python -m moshi.v2_demo
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .v2.generate import generate_person, trajectory_signature
from .v2.state import DIM_NAMES


def show_trajectory(result: dict, title: str) -> None:
    print(f"\n───── {title} ─────")
    print(f"性情基线 P：{result['baseline'].describe()}")
    print(f"初始状态 S0：{result['state0'].describe()}")
    print("一生轨迹（每站：状态 + 事件）：")
    for st in result["steps"]:
        anchor_mark = "  ← 锚点" if st.is_anchor else ""
        print(f"  {st.age:>2}岁  {st.domain:<6} S={st.state.describe()}  {st.event_note}{anchor_mark}")


def main() -> None:
    print("=" * 66)
    print("  Moshi V2 · 线性演化内核 —— 状态在移动，不再是选择拼装")
    print("=" * 66)

    seed = 20260827
    r1 = generate_person(seed)
    r2 = generate_person(seed)

    # 验证 1：同种子 → 同一轨迹（确定性可复现）
    sig1 = trajectory_signature(r1)
    sig2 = trajectory_signature(r2)
    print(f"\n【验证 1】同种子({seed})复现：轨迹签名相等？ → {sig1 == sig2}")

    show_trajectory(r1, "陈默识 · 一生（种子 {seed}）".format(seed=seed))

    # 验证 2：状态是否真的在移动（不是恒定/无变化）
    states = [st.state.as_list() for st in r1["steps"]]
    moved = any(any(abs(a - b) > 1e-6 for a, b in zip(s1, s0))
                for s0, s1 in zip(states, states[1:]))
    print(f"\n【验证 2】状态在逐步移动（演化）？ → {moved}")
    anchors = [st for st in r1["steps"] if st.is_anchor]
    print(f"【验证 3】锚点数（|ΔS| 大的显著弯曲点）= {len(anchors)}")
    for a in anchors:
        print(f"    · {a.event_note}")


if __name__ == "__main__":
    main()
