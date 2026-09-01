"""V4 记忆层（memory）—— 她"记得"什么（乙定位：无全知档案）。

对应设计（乙）：
- 她不客观知道自己——没有"我的人生脉络"这个概念；她只**记得**自己经历的具体事情，
  并带着由此长成的**性格认识**去生活。
- 记忆来源：V3 人生轨迹里的**重大事件**（大事年）+ 认识（Beliefs）。
- 记忆有**温度**：她记得的事未必完整客观——就像人一样，记得的往往带情绪。

注意（诚实边界）：V4 用"规则+模板"，是**最小验证**。真实系统应让大模型在
"她记忆的事实"约束下以她的口吻生成（结构归规则，质感归大模型，可插拔）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..v0.belief import Belief


@dataclass
class Memory:
    """一条"她记得的事"。"""
    year: int | None          # 具体年份（若知道）
    age: int                  # 那时她几岁
    text: str                 # 她记得的内容（带她视角/情绪的表述）
    domain: str | None = None # 关联领域（用于"被问到时想起什么"）
    vividness: float = 0.5    # 记忆的鲜明度（越鲜明越容易被想起/提起）


# ── 乙-B：阶层一致性改写（facts 与记忆"同源"的轻量实现）──

# 无矛盾版本（按引用顺序依次替换第一个命中）
_MONEY_REPLACEMENTS: dict[str, str] = {
    "家里为钱吵了一架，她第一次知道钱的重量":
        "家里为钱的事有过争执，她第一次意识到钱在生活里的分量",
    "她不得不为一份糊口的工作，把很多事先放下":
        "她不得不先为工作的事忙起来，把很多自己的事先放下",
    "为了一笔能糊口的钱":
        "为了一笔生活费",
}


def _soften_for_class(text: str, facts) -> str:
    """若家庭阶层=小康/富足，把"缺钱/糊口"式表述弱化为一致版本。"""
    if facts is None or facts.family_class not in ("小康", "富足"):
        return text
    for src, dst in _MONEY_REPLACEMENTS.items():
        if src in text:
            return text.replace(src, dst)
    # 通用弱化：出现"糊口/供不起/为钱吵"时替换关键词
    if "糊口" in text:
        text = text.replace("糊口", "能安稳")
    if "家里供不起" in text:
        text = text.replace("家里供不起", "家里在支持上不太宽裕")
    if "为钱吵了一架" in text:
        text = text.replace("为钱吵了一架", "为钱的事有过争执")
    if "为生计奔波" in text:
        text = text.replace("为生计奔波", "为生活忙碌")
    return text


def build_memories(result: dict[str, Any], facts=None) -> list[Memory]:
    """从人生轨迹（大事年）+ 认识构建她的记忆。

    乙定位：她只记得"发生过的事"，不整理成"人生档案"。
    只取大事年（is_major）——平凡年大多被消化，记不住（符合真实人的记忆）。
    facts（乙-B）：用于**阶层一致性改写**——"金钱/生计"类记忆与家庭阶层同源，消除
    "医生护士家庭却为钱糊口"这类矛盾。（轻量实现；完整同源生成有待 V5。）
    """
    memories: list[Memory] = []
    for st in result["steps"]:
        if not st.is_major:
            continue
        # 跳过"平静的日子"（这不是记忆，是可回忆的事）
        if "平静" in st.event_note or st.event_note == "":
            continue
        # 她视角的记忆表述：沿用事件叙事；并按家庭阶层做一致性改写（乙-B）
        note = st.event_note
        if facts is not None:
            note = _soften_for_class(note, facts)
        memories.append(Memory(
            year=st.year,
            age=st.age,
            text=note,
            domain=st.domains[0][0] if st.domains else None,
            vividness=0.6 if st.is_anchor else 0.4,   # 锚点事件更鲜明
        ))
    return memories


def build_beliefs(result: dict[str, Any]) -> list[Belief]:
    """从投影器拿到她的性格认识（自带张力、非标签）。"""
    from ..v3.project import project_beliefs
    return project_beliefs(result)
