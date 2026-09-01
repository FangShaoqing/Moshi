"""V2 世界模型（world）—— 不提供"候选池"，提供"交互产生事件"的机制。

关键转变（区别于 V1）：
- V1：事件是从候选池里"选"一个（= 离散选择）。
- V2：事件强度 e = 世界 x 行为的交互函数（= 由状态与世界共同"计算"出来），
        它随当前状态而变，不是事先列好的标签。

这里的世界极简：一组"情境"（domain），每个情境知道"它会对状态的哪些维度施加多大影响"。
事件强度 = 由"探索/投入度"（来自状态）x "情境的响应"算出来。

注意：V2 的世界是"占位"的（手工小定义），真实系统里它来自"真实世界知识层 + 她与世界的交互"。
"""

from __future__ import annotations

from dataclasses import dataclass

from .state import StateVector, DIM_NAMES


@dataclass
class Situation:
    """一个"情境域"。世界层面：情境决定"如果她在这个情境里投入，状态会被往哪推"。"""
    name: str
    # 如果"投入度高"，对 6 个状态维度的作用（如：亲密关系投入高 → Trust+、Valence+，但也可能因落差带走 Dominance-）
    push_when_invested: tuple[float, ...] = (0.0,) * len(DIM_NAMES)
    # 如果"受挫/被拒绝"，对 6 个维度的作用（负面事件在动力学里以"低响应/挫败感"表达）
    push_when_frustrated: tuple[float, ...] = (0.0,) * len(DIM_NAMES)


# 世界情境表（V2 占位，极少；真实系统由真实世界知识层提供）
# 注意：push 系数是"这件事对状态的显著影响"量级（0.2~0.4），
# 要足以"让一件事留下痕迹"（重大事件 → 显著弯曲），而非微调。
SITUATIONS: dict[str, Situation] = {
    "信任": Situation(
        name="信任",
        # 被信任/被托付 → 安全感 + 信任 + 归属 + 愉悦
        push_when_invested=(0.22, 0.12, 0.10, 0.24, 0.36, 0.30),
        # 被背叛 → 信任↓、愉悦↓、归属↓、支配微升（警觉）
        push_when_frustrated=(-0.30, 0.10, 0.14, -0.22, -0.42, -0.26),
    ),
    "亲密关系": Situation(
        name="亲密关系",
        push_when_invested=(0.26, 0.22, -0.04, 0.22, 0.30, 0.26),
        push_when_frustrated=(-0.34, -0.14, -0.08, -0.26, -0.22, -0.22),
    ),
    "工作与生计": Situation(
        name="工作与生计",
        push_when_invested=(0.14, 0.30, 0.34, 0.30, 0.08, 0.04),
        push_when_frustrated=(-0.22, -0.26, -0.18, -0.30, -0.04, 0.00),
    ),
    "金钱": Situation(
        name="金钱",
        push_when_invested=(0.08, 0.14, 0.26, 0.18, 0.04, 0.04),
        push_when_frustrated=(-0.18, -0.08, -0.14, -0.18, -0.04, 0.00),
    ),
    "自我价值": Situation(
        name="自我价值",
        push_when_invested=(0.22, 0.14, 0.22, 0.38, 0.12, 0.12),
        push_when_frustrated=(-0.26, 0.00, -0.04, -0.38, -0.08, -0.04),
    ),
    "归属": Situation(
        name="归属",
        push_when_invested=(0.22, 0.10, 0.04, 0.22, 0.26, 0.42),
        push_when_frustrated=(-0.26, -0.04, 0.00, -0.12, -0.12, -0.34),
    ),
    "未来": Situation(
        name="未来",
        push_when_invested=(0.18, 0.26, 0.26, 0.22, 0.04, 0.08),
        push_when_frustrated=(-0.22, -0.18, -0.12, -0.22, -0.04, 0.00),
    ),
    "表达自我": Situation(
        name="表达自我",
        push_when_invested=(0.22, 0.30, 0.18, 0.26, 0.08, 0.08),
        push_when_frustrated=(-0.26, -0.12, -0.08, -0.26, -0.04, 0.00),
    ),
}


def event_intensity(state: StateVector, domain: str, invested: float) -> tuple[float, ...]:
    """交互函数：情境 x 行为 → 事件对状态的"推向量"。

    V1 是从候选池"选"一个标签；V2 是"计算"一个向量 ——
    intensity = push_when_invested * invested + push_when_frustrated * (1 - invested)
    其中 invested 由"状态"读出的"投入度"决定（她此刻的状态把多大动力投向这个情境）。
    这样事件强度是连续变化的、随状态而变的 —— 不是从有限列表里选的。
    """
    sit = SITUATIONS.get(domain)
    if sit is None:
        return (0.0,) * len(DIM_NAMES)
    inv = tuple(a * invested + b * (1.0 - invested)
                for a, b in zip(sit.push_when_invested, sit.push_when_frustrated))
    return inv


def effective_investment(state: StateVector, domain: str) -> float:
    """从状态读出"她在这个情境上的投入度"（行为倾向的内核）。

    每个情境与状态的不同维度相关，V2 用一个简化的线性读出：
    用"自我价值+信任+归属"作为通用投入倾向，再按情境微调。
    （真实系统：行为倾向 h(S_t) 是状态→行为的非线性映射，此处先线性。）
    """
    # 基础投入 = 自我价值(0.5) + 信任(0.3) + 归属(0.3) + 唤醒(0.2) 归一
    base = (0.5 * state.self_worth + 0.3 * state.trust + 0.3 * state.belonging
            + 0.2 * state.arousal)
    # 情境微调（占位）：越有"主导"的情境，投入越高
    return max(0.0, min(1.0, base + 0.1 * state.dominance))
