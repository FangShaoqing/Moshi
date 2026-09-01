"""V0 · 最小原型演示 —— 人格从经历中涌现的"灵魂"验证。

用途：用几个预设经历（种子事件）+ 一套硬编码的"事件→认识"映射规则，
观察它能否沉淀出一个"具体、非标签、有厚度、可矛盾"的人（陈默识）。

运行：  python -m moshi.v0_demo
"""

from __future__ import annotations

import sys

# 强制 UTF-8 输出，避免中文在 GBK 终端下乱码。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .belief import CONTROLLED_DOMAINS
from .person import Person
from .life.event_rules import apply_event


def build_life_arc(person: Person) -> None:
    """按"人生真实顺序"把经历喂给她，形成一条可回溯的一生片段。"""
    # 顺序即因果顺序：早年贫寒 → 家庭 → 16岁被信任的人背叛 → 17岁辍学打工 → 20岁被温柔接纳
    apply_event(person, "grew_up_poor", age=0,
                narrative="出生在一个并不宽裕的家庭，从小看她为生计发愁")
    apply_event(person, "trust_betrayed_at_16", age=16,
                narrative="被一个她最信任的人背叛，她第一次明白'交出去'很危险")
    apply_event(person, "dropped_out_to_work_at_17", age=17,
                narrative="家里供不起，她辍学早早去打工，为生计奔波")
    apply_event(person, "was_gently_accepted_at_20", age=20,
                narrative="后来遇到一个没有因为她的过去而离开她的人，第一次被温柔接纳")


def main() -> None:
    print("=" * 62)
    print("  Moshi V0 · 最小原型 —— 人格从经历中涌现（灵魂验证）")
    print("=" * 62)

    moshi = Person(name="陈默识")

    print("\n【第一步】用受控词表定义'情境域'（domain）：")
    print("  " + " / ".join(sorted(CONTROLLED_DOMAINS)))

    print("\n【第二步】按人生顺序喂经历，看她沉淀出哪些认识：")
    build_life_arc(moshi)

    print("\n\n" + "=" * 62)
    print("  最终人格 —— 陈默识（由经历累积出的若干条认识/倾向）")
    print("=" * 62)
    moshi.show_person()

    print("\n【灵魂自检】她是一个'具体的人'而非'一堆标签'吗？")
    for b in moshi.beliefs:
        # 每条都是条件式：因为[经历]，所以在[情境]下倾向[做法]
        print(f"  OK 非标签：{b.as_condition()}")


if __name__ == "__main__":
    main()
