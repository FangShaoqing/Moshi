"""Person（陈默识的人格载体）—— 由一系列 Belief（认识/倾向）累积而成。

V0 定位：用一套硬编码的"事件 → 认识映射"，把若干预设经历，沉淀成一个
"具体、非标签、有厚度"的人。用来观察：人格从经历中涌现这个灵魂是否成立。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .belief import Belief


@dataclass
class Person:
    """她本身。V0 只承载"认识集合"，为最小灵魂验证而设。"""

    name: str = "陈默识"
    beliefs: list[Belief] = field(default_factory=list)

    def add_belief(self, belief: Belief) -> None:
        self.beliefs.append(belief)

    @property
    def belief_count(self) -> int:
        return len(self.beliefs)

    def summary_condition_lines(self) -> list[str]:
        """每条认识都以"条件式"输出（非标签）。"""
        return [b.describe() for b in self.beliefs]

    def show_person(self) -> None:
        print(f"===== 陈默识 · 人格（由 {self.belief_count} 条认识/倾向累积） =====")
        for i, b in enumerate(self.beliefs, 1):
            print(f"\n[{i}] {b.describe()}")
            if b.tension:
                print(f"     ↳ 张力：{', '.join(b.tension)}")
        print("\n===== 结尾 =====")
