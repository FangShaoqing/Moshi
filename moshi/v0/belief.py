"""Belief（一条认识/倾向）—— 人格从经历中涌现的最小可校验单元。

按设计 14 定稿：
- 非标签：cause(经历) + domain(情境域) + tendency(倾向) 组合成条件式，而非判断句。
- 有厚度：tension 允许矛盾并存。
- 因果可溯：每条认识挂在 cause（触发经历）上。
- 可校验：domain 用受控词表；tendency 受控候选为主 + 有限自由。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# 受控词表：情境域（domain）。V0 先给一个最小集合，可扩展。
CONTROLLED_DOMAINS = {
    "亲密关系",     # 恋人 / 好友 / 家人等亲近的对象
    "工作与生计",   # 职业、生计、生存
    "金钱",         # 对钱、物质、安稳的态度
    "自我价值",     # 我是谁、我值不值得、配不配
    "信任",         # 对他人诚意、可靠性的判断
    "归属",         # 我属于哪里、被谁接纳
    "未来",         # 对将来、理想的预期
    "表达自我",     # 敢不敢表达自己、被听见
}


@dataclass
class Belief:
    """一条"认识/倾向"。"""

    id: str
    cause: str                 # 触发经历（哪段经历形成/强化了它）
    domain: str                # 情境域（受控词表）
    tendency: str              # 倾向（受控候选为主 + 有限自由）
    attribution: str           # 归因（她为什么这样想）
    strength: float            # 强度（多牢固，0~1；慢变量）
    salience: float            # 活跃度（此刻多活跃，0~1；随情境波动）
    formed_at: int             # 形成时间/年龄
    tension: list[str] = field(default_factory=list)   # 与哪些认识矛盾

    def __post_init__(self) -> None:
        # 轻量校验：domain 必须来自受控词表，strength/salience 必须在 [0,1]
        if self.domain not in CONTROLLED_DOMAINS:
            raise ValueError(
                f"domain '{self.domain}' 不在受控词表中。可选：{sorted(CONTROLLED_DOMAINS)}"
            )
        for name in ("strength", "salience"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} 必须在 [0,1]，当前为 {v}")

    def as_condition(self) -> str:
        """把这条认识表述成"条件式"（非标签）：因为[经历]，所以在[情境]下倾向[做法]。"""
        return (f"因为「{self.cause}」，所以在「{self.domain}」上，她倾向于「{self.tendency}」"
                f"（归因：{self.attribution}；强度 {self.strength:.2f}）")

    def describe(self) -> str:
        return self.as_condition()
