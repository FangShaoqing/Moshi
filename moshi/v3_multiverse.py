"""V3 · 多元宇宙演示 —— 多个种子，多个命运。

一次生成 N 个"陈默识"（不同种子 = 不同命运走向），并排列出它们的命运摘要：
- 世界运势（顺/逆风底色）
- 人生事件时间线（具体叙事）
- 最终她长成了什么样（最终状态人话摘要）

用来感受"混沌演化"的核心：**近种子不必看，不同种子 → 完全不同的人。**

运行：  python -m moshi.v3_multiverse [数量]
例如：  python -m moshi.v3_multiverse 8
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .v3.generate import generate_person
from .v3.project import project_beliefs
from .v2.state import DIM_NAMES

CN_DIMS: dict[str, str] = {
    "Valence": "愉悦", "Arousal": "活力", "Dominance": "主导",
    "SelfWorth": "自我", "Trust": "信任", "Belonging": "归属",
}


def person_summary(result: dict) -> str:
    """把最终状态翻译成一句人话：哪些维度高/低。"""
    final = result["steps"][-1].state
    v = dict(zip(DIM_NAMES, final.as_list()))
    highs = [CN_DIMS[n] for n in DIM_NAMES if v[n] >= 0.55]
    lows = [CN_DIMS[n] for n in DIM_NAMES if v[n] <= 0.35]
    parts = []
    if highs:
        parts.append("偏强：" + "、".join(highs))
    if lows:
        parts.append("偏弱：" + "、".join(lows))
    return "；".join(parts) if parts else "中性（起伏但整体均衡）"


def show_universe(seed: int, idx: int) -> None:
    result = generate_person(seed)
    print(f"\n{'─' * 70}")
    print(f"🌌 宇宙 #{idx}  种子={seed}")
    print(f"{'─' * 70}")
    # 出生日期与"当下的她"
    print(f"    她出生于 {result['birth_date']}（{result['current_age']} 岁，今天是 {result['now']}）")
    # 世界运势（只挑当前顺/逆风显著的）
    fav = [d for d, r in result["world"].responses.items() if r > 0.15]
    adv = [d for d, r in result["world"].responses.items() if r < -0.15]
    print(f"    世界底色：顺风「{'、'.join(fav) if fav else '无'}」 逆风「{'、'.join(adv) if adv else '无'}」")
    print(f"    她的人生：")
    for st in result["steps"]:
        if not st.is_major:
            continue   # 平凡年折叠（省略显示，保持"重点突出"）
        mk = " ★" if st.is_anchor else ""
        yr = f"{st.year}" if st.year else f"{st.age}岁"
        print(f"      {yr}年（{st.age}岁）  {st.event_note}{mk}")
    mundane = sum(1 for st in result["steps"] if not st.is_major)
    if mundane:
        print(f"      …… 其间还有 {mundane} 个平平淡淡的年份（日常被消化）……")
    final = person_summary(result)
    print(f"    现在的她（{result['current_age']} 岁）：{final}")
    # 认识投影（灵魂可读化）
    beliefs = project_beliefs(result)
    print(f"    她长出的认识（{len(beliefs)} 条）：")
    for b in beliefs:
        tension = f"  [张力:{'/'.join(b.tension)}]" if b.tension else ""
        print(f"      · {b.as_condition()}{tension}")


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    print("=" * 70)
    print(f"  Moshi V3 · 多元宇宙 —— {n} 个种子，{n} 个命运（混沌演化的直接展示）")
    print("=" * 70)
    seeds = [20260827 + i * 7 for i in range(n)]   # 间隔 7，避免种子过近
    for i, s in enumerate(seeds, 1):
        show_universe(s, i)


if __name__ == "__main__":
    main()
