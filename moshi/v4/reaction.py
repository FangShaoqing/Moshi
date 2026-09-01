"""V4 反应模型（reaction）—— 她的人性瑕疵：敷衍/撒谎/沉默/无语。

设计（26）：她的人生事实不可编造（校验器管），但她的人际行为可以有瑕疵
（敷衍/善意隐瞒/沉默/无语）——真实人性。
- 规则层：根据"你的话（冒犯度/接不住度）"与"她的状态（信任/心情）"决定本次反应类型；
- LLM 层：在该类型内生成（如"善意隐瞒"→"我没事"；"沉默"→停顿不接）。

触发因素：
- 冒犯度：你的话是否越界（辱骂/过分打听/轻蔑）——高冒犯 → 沉默/无语；
- 接不住度：话题触及她不愿谈、或你让她无语——高接不住 → 敷衍/岔开；
- 状态：信任低 + 你问隐私 → 敷衍避开；心情低落 + 你问"还好吗" → 善意隐瞒。
"""

from __future__ import annotations

import re

from .person import Person

# 五种反应类型
REACTIONS = ("sincere", "dodge", "conceal", "silent", "speechless", "angry")
# 中文名（展示用）
REACTION_NAMES = {
    "sincere": "真诚回应",
    "dodge": "敷衍避开",
    "conceal": "善意隐瞒",
    "silent": "沉默停顿",
    "speechless": "无语岔开",
    "angry": "生气",
}

# 冒犯词（真正冒犯/人身攻击 → 生气）
_ROUGH_WORDS = ("你算", "呵呵", "无聊", "烦不烦", "闭嘴", "有病", "蠢", "滚", "傻",
                "无趣", "也就这样", "没意思", "你这种人", "你这个人真")
# 过分打听（隐私/越界）——含"问她的家庭/关系"（刚认识问这些 = 过分）
_INTRUSIVE_WORDS = ("你几岁", "体重", "收入", "存款", "工资", "别墅", "房",
                    "相亲", "前任", "彩礼", "收入多少", "多少钱", "有没有钱",
                    "你家里的钱", "工资多少", "房子多大", "开什么车",
                    "你妈", "你妈妈", "你爸妈", "你家人", "你家里", "你室友",
                    "你爸", "你父亲", "你妹妹", "你哥哥", "你朋友", "你对象")
# 让她"接不住"的（单方面宣泄/说教/轻蔑其生活）
_UNCOMFORTABLE = ("你应该", "女人就该", "你太敏感", "你想多了", "至于吗", "别矫情",
                  "你活该", "你这人", "我早就说过", "呵呵", "也就这样")


def _score_hits(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for w in words if w in text)


def evaluate_reaction(person: Person, user_input: str,
                      history: list[dict] | None = None,
                      intent: str = "chat") -> str:
    """决定本次反应类型（规则层；LLM 在其内生成）。

    - **真正冒犯/人身攻击 → 生气（angry）**：内敛的怒（冷、钝、带刺、藏起）——生气是真实的，
      不是"无语"顶替；且会**持续**（这轮气不消，下轮仍冷）；
    - 说教/轻蔑/接不住 → 无语/沉默；
    - 隐私 + 低信任 → 敷衍；心情低落被问 → 善意隐瞒；否则 → 真诚。
    """
    history = history or []
    rough = _score_hits(user_input, _ROUGH_WORDS)
    intr = _score_hits(user_input, _INTRUSIVE_WORDS)
    unc = _score_hits(user_input, _UNCOMFORTABLE)

    # 0. 持续冷场：上一轮她生气了 → 这轮还在气（除非你真诚道歉/挽回）
    if getattr(person, "is_angry", False):
        # 你道歉 → 她气会消一点，但不会立刻全消
        if any(w in user_input for w in ("对不起", "抱歉", "我错了", "别生气", "我来赔不是", "是我不好")):
            person.is_angry = False
            person.angry_turns = 0
            return "sincere"
        person.angry_turns = getattr(person, "angry_turns", 0) + 1
        # 持续生气 → 气耗尽：怒转"彻底凉"（exhausted——不是怒气，是伤透了/没力气了）
        if person.angry_turns >= 3:
            person.is_angry = False
            person.exhausted = True
            try:
                from ..v2.state import StateVector
                s = person.state.as_list() if person.state else [0.5] * 6
                s[0] = max(0.0, min(1.0, s[0] - 0.12))   # Valence 更低（凉）
                s[1] = max(0.0, min(1.0, s[1] - 0.10))   # Arousal 更低（没力气）
                person.state = StateVector(*s)
            except Exception:
                pass
            return "silent"   # 凉了 → 沉默（比怒更冷）
        return "angry"

    # 1. 真正冒犯/人身攻击 → 生气（真实愤怒；不是"无语"顶替）
    if rough >= 1:
        person.is_angry = True
        person.angry_turns = 0
        # 情绪状态联动：真怒写进状态（Arousal↑、Valence↓——生气有生理/情绪痕迹）
        try:
            from ..v2.state import StateVector
            s = person.state.as_list() if person.state else [0.5] * 6
            s[0] = max(0.0, min(1.0, s[0] - 0.15))   # Valence↓（不悦）
            s[1] = max(0.0, min(1.0, s[1] + 0.12))   # Arousal↑（激动）
            s[2] = max(0.0, min(1.0, s[2] + 0.08))   # Dominance↑（想反击/立起防御）
            person.state = StateVector(*s)
        except Exception:
            pass
        return "angry"
    # 2. 说教/轻蔑/接不住 → 无语（或沉默）
    if unc >= 1:
        return "speechless" if "就应该" not in user_input else "silent"
    # 3. 隐私追问 → 不适（真实人问收入/体重/家庭，即使有一定信任也不舒服）
    #    信任低 → 敷衍；信任高 → 也会不自然（委婉拒绝/轻带过——由 dodge 表达）
    if intr >= 1:
        return "dodge"
    # 4. 心情低落 + 问"还好吗" → 善意隐瞒
    if intent in ("ask_now", "comfort"):
        try:
            state = person.state.as_list()
            if state[0] < 0.45:
                return "conceal"
        except Exception:
            pass
    # 5. 默认真诚
    return "sincere"
