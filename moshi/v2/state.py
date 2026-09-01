"""V2 状态向量（state）—— 陈默识在任意时刻"是什么"的连续表示。

对应设计：
- 15（线A）：状态 = 连续向量 S ∈ R^n，演化 = 方程变换，而非"往列表追加"。
- 维度（协作方已确认 6 维）：VAD 情绪三轴 + 自我价值/信任/归属（关系-自我维度）。

注意：S 是"连续、会移动"的向量，不是标签列表。它的移动方向由动力学决定。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# 6 个维度的名称（顺序固定，全项目统一）
DIM_NAMES: tuple[str, ...] = (
    "Valence",      # 愉悦度
    "Arousal",      # 唤醒度
    "Dominance",    # 支配度
    "SelfWorth",    # 自我价值
    "Trust",        # 信任倾向
    "Belonging",    # 归属感
)

N_DIMS = len(DIM_NAMES)


@dataclass
class StateVector:
    """人格/情绪/动机的状态向量。S ∈ R^6。

    每个维度取值区间约定为 [-1, 1] 或 [0, 1]？—— 用 [0,1] 更直观：0=几乎没有，1=很强。
    （V2 用 [0,1]，方便读；负向情绪用"低 Valence"表达，而非负值。）
    """
    valence: float
    arousal: float
    dominance: float
    self_worth: float
    trust: float
    belonging: float

    def as_list(self) -> list[float]:
        return [self.valence, self.arousal, self.dominance,
                self.self_worth, self.trust, self.belonging]

    def clamp(self, lo: float = 0.0, hi: float = 1.0) -> "StateVector":
        """把所有维度夹到 [lo, hi]，保证状态不越界（世界约束）。"""
        vals = [min(hi, max(lo, v)) for v in self.as_list()]
        return StateVector(*vals)

    def scale(self, c: float) -> "StateVector":
        return StateVector(*(v * c for v in self.as_list()))

    def add(self, other: "StateVector") -> "StateVector":
        return StateVector(*(a + b for a, b in zip(self.as_list(), other.as_list())))

    def diff(self, other: "StateVector") -> "StateVector":
        return StateVector(*(a - b for a, b in zip(self.as_list(), other.as_list())))

    def describe(self) -> str:
        return " / ".join(f"{n}={v:.2f}" for n, v in zip(DIM_NAMES, self.as_list()))


def make_state(**kwargs) -> StateVector:
    """按维度名构造 StateVector（未给的默认 0.5，中性起点）。"""
    values = {n: kwargs.get(n.lower(), 0.5) for n in DIM_NAMES}
    return StateVector(**values)
