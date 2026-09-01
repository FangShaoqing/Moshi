"""V4 记忆提取器（extract）—— 从对话中提取"你告诉她的关于你的事"。

交互深化的关键：她记住**你**。检测用户消息是否是"自我暴露"（告诉了她关于你的事），
提取为可引用的一句话，存入 Person.shared_memories。

规则（V4 最小验证）：
- 含"我"且是自我分享类句式（"我在/我喜欢/我最近/我小时候/我和/我有个/我在XX工作/我爸妈…"）；
- 长度足够（>12 字）且不像单纯问题；
- 提取后由 LLM 后续引用（system prompt 注入"她记得的事"）。
"""

from __future__ import annotations

import re

# 自我暴露启动词（"我"字开头 + 常见宣示范式）
_SELF_CLAUSES = (
    "我在", "我喜欢", "我最", "我最近", "我小时候", "我爸妈", "我和", "我有个",
    "我养", "我住", "我工作", "我上班", "我家里", "我老家", "我朋友", "我同事",
    "我现在", "我已经", "我一直", "我特别", "我打算", "我刚", "我常常", "我总",
)


def extract_self_disclosure(user_input: str) -> str | None:
    """若用户消息是"自我暴露"类 → 返回可记忆的短句；否则 None。

    只提取"关于你的可记忆事实"，不提取问题/寒暄/情绪宣泄（那些不形成"她记得你什么"）。
    """
    text = user_input.strip()
    if len(text) < 6:      # 降低：短自我暴露（"我养了一只猫"）也应被记住
        return None
    # 排除明显是提问（以"你/怎么/什么/哪/吗"结尾或开头）
    if text.endswith(("？", "吗", "呢", "吧")) and not re.match(r"^我", text):
        return None
    if not any(cls in text for cls in _SELF_CLAUSES):
        return None
    # 太长截断到 60 字（记忆是短句）
    if len(text) > 60:
        text = text[:57] + "…"
    return text


def remember_from_input(person, user_input: str) -> bool:
    """尝试把用户消息记成"她记得你的事"。返回是否记住。"""
    fact = extract_self_disclosure(user_input)
    if fact is None:
        return False
    person.remember_about_you(fact, weight=0.5)
    return True
