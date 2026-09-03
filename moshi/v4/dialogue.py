"""V4 对话引擎（dialogue）—— 意图分类 + 披露模型 + 回应生成（混合：规则定边界，LLM 给口吻）。

设计（协作方确认）：
1. 混合（C）：**规则决定边界**（隐瞒/披露多深——隐藏宇宙），**LLM（DeepSeek）在边界内以她的口吻生成**；
   无 LLM（未配置/失败）→ 规则模板兜底（MVP 最小可跑）。
2. **真实人际披露模型**（本次重构核心）：不会因一句"你家在哪"就聊起过去。披露取决于五因素：
   - 侵入性（问题多冒犯）：什么是低（名字）→ 高（背叛/感情史）
   - 信任度（交互积累）
   - 疼痛度（记忆的"伤疤"程度）：高痛记忆难开口
   - 对等性（你有没有也敞开过自己 reciprocity）
   - 场合感（问题是否自然从话题浮现）
   三个结果：**轻带过**（默认，未达门槛）/ **浅露端倪**（部分达标，收着说）/ **深谈**（信任高+时机好+疼痛可承受）。
3. 乙（无全知档案）：她只凭记忆和性格回应，不会盘点自己。
"""

from __future__ import annotations

import re
from typing import Any, Callable

from .person import Person
from .memory import Memory
from .llm import generate_reply_llm, llm_available
from .reaction import evaluate_reaction

# ── 意图分类（关键词规则；Mvp 最小）──
# "过去类"词优先（避免"现在还想相信人吗"被误判为 ask_now）。
# 家庭/关系类话题也归入 ask_past（她们世界的人/过去是隐私——披露模型接管，非普通聊天）。
PAST_WORDS = ("小时候", "以前", "过去", "你记得小时候", "你记得以前", "你家", "爸妈",
              "童年", "以前的事", "之前", "那时候", "相信过", "背叛", "受过伤",
              "还相信", "相信人", "信任",
              "妈妈", "我妈", "父亲", "我爸", "家人", "家里", "室友", "朋友", "同学",
              "妹妹", "哥哥", "弟弟", "姐姐")

INTENT_RULES: dict[str, tuple[str, ...]] = {
    "greeting": ("你好", "嗨", "哈喽", "早", "晚上好", "在吗", "hi", "hello"),
    "ask_now": ("现在", "最近", "今天", "在干嘛", "还好吗", "怎么样", "忙"),
    "ask_personal": ("你叫什么", "你是谁", "你几岁", "多大了", "生日", "哪里人", "你哪的"),
    "comfort": ("难过", "累", "不开心", "烦", "压力", "伤心", "哭"),
    "chat": ("天气", "吃饭", "喜欢", "觉得", "周末", "工作"),
}


def classify(user_input: str) -> str:
    # 用户分享自己（"我..." + 倾诉/自我暴露类）→ 优先看作"倾诉/分享"，触发对等性
    # 改：count("我")≥1（句首"我"+倾诉即分享——"我最近真的好累"这类短而深的也算）
    if len(user_input) >= 8 and user_input.count("我") >= 1:
        if any(w in user_input for w in ("累", "烦", "难过", "好累", "压力", "开心", "喜欢", "觉得", "最近", "在", "想")):
            return "user_share"
    for w in PAST_WORDS:
        if w in user_input:
            return "ask_past"
    for intent, words in INTENT_RULES.items():
        for w in words:
            if w in user_input:
                return intent
    return "chat"


# ── 记忆检索（她"记得"的，有依据）──
def retrieve_memories(person: Person, intent: str, query: str) -> list[Memory]:
    domain_kw: dict[str, tuple[str, ...]] = {
        "信任": ("背叛", "朋友", "相信", "承诺"),
        "亲密关系": ("喜欢", "恋爱", "关系", "他", "她"),
        "工作与生计": ("工作", "挣钱", "打工", "生计"),
        "金钱": ("钱", "缺钱", "攒"),
        "自我价值": ("自己", "我行", "配", "努力"),
        "归属": ("家", "地方", "一个人", "圈子"),
        "未来": ("以后", "理想", "未来", "打算"),
        "表达自我": ("说", "心里话", "表达", "话"),
    }
    scored = []
    for m in person.memories:
        score = 0.0
        if m.domain:
            for kw in domain_kw.get(m.domain, ()):
                if kw in query:
                    score += 1.0
        else:
            for w in re.findall(r"[\u4e00-\u9fa5]{2,}", query):
                if w in m.text:
                    score += 0.5
        scored.append((score, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    hits = [m for s, m in scored if s > 0][:3]
    if not hits and person.memories:
        most_vivid = max(person.memories, key=lambda m: m.vividness)
        hits = [most_vivid]
    return hits


# ── 披露模型（真实人际边界：五因素 → 轻带过/浅露/深谈）──

def _intrusiveness(intent: str, query: str) -> float:
    """问题的侵入性：0（无）~ 1（最高）。"""
    if intent != "ask_past":
        return 0.0
    high = ("背叛", "受伤", "伤害", "感情", "恋爱", "分手", "恨", "秘密", "哭",
            "我妈", "你妈", "你爸妈")
    mid = ("家", "爸妈", "童年", "小时候", "朋友", "家里", "妈妈", "父亲",
           "家人", "室友", "对象", "家人")
    for w in high:
        if w in query:
            return 1.0
    for w in mid:
        if w in query:
            return 0.55
    return 0.4   # 泛指过去 = 中等侵入


def _memory_pain(memory: Memory) -> float:
    """记忆的疼痛度：0（无害）~ 1（伤疤）。"""
    pain_words = ("背叛", "辜负", "离开", "没有来", "嘲笑", "笨", "否定",
                  "吵架", "钱", "欠", "孤单", "一个人", "咽", "疼")
    t = memory.text if memory else ""
    hits = sum(1 for w in pain_words if w in t)
    return min(1.0, hits * 0.3)


def _reciprocity(history: list[dict]) -> float:
    """对等性：你有没有也敞开过自己（用户消息里"说自己的事"）。

    V4 简化：用 extract 的自我暴露检测（含"我"类启动词 + 非提问），
    能识别"我爸妈也常吵架"这种短而深的暴露（此前要求 >15 字会漏掉深谈场景）。"""
    try:
        from .extract import extract_self_disclosure
    except Exception:
        extract_self_disclosure = None
    score = 0.0
    for m in history[-6:]:
        if m["role"] != "user":
            continue
        text = m["content"]
        if extract_self_disclosure is not None:
            if extract_self_disclosure(text):
                score += 0.25
        else:
            if text.count("我") >= 1 and len(text) >= 6:
                score += 0.25
    return min(1.0, score)


def _fit_context(history: list[dict], query: str) -> float:
    """场合感：问题是否自然从话题浮现（连续多轮同话题/用户继续追问）。"""
    if len(history) < 2:
        return 0.3   # 一上来就问过去 = 突兀
    recent_user = [m for m in history[-3:] if m["role"] == "user"]
    if len(recent_user) >= 2:
        return 0.7   # 聊了几轮 = 自然些
    return 0.5


def evaluate_disclosure(person: Person, intent: str, query: str,
                        history: list[dict]) -> dict:
    """计算披露等级：'avoid'（轻带过）/ 'hint'（浅露端倪）/ 'share'（深谈）。"""
    if intent != "ask_past":
        return {"level": "avoid", "score": 0.0}
    inv = _intrusiveness(intent, query)      # 侵入性（高=难）
    pain = 0.0                                # 疼痛度（取相关记忆平均，若未检索则随侵入性）
    trust = person.trust                      # 信任度
    recip = _reciprocity(history)             # 对等性
    fit = _fit_context(history, query)        # 场合感

    # 披露意愿分（加权；侵入性、疼痛是负项）。
    # 设计意图：初期大多"轻带过"（不是"深闭口"——真实人被问到会稍作回应），
    # 信任+对等+时机到位时才"浅露"；深谈需要相当信任+对等。
    # 长期陪伴：关系阶段越亲近，越愿意敞口（stage_bonus）。
    # 依恋联动：焦虑型怕失去→更愿倾诉；回避型→更不愿展开。
    try:
        attach_bonus = person.attachment_modulation().get("disclosure_bonus", 0.0)
    except Exception:
        attach_bonus = 0.0
    score = (
        trust * 0.25
        + recip * 0.35
        + fit * 0.25
        + person.stage_bonus()      # 关系阶段加成（初识0 → 深入0.30）
        + attach_bonus              # 依恋联动
        - inv * 0.20
        - pain * 0.15
    )
    # 门槛：轻带过(avoid 的"淡淡回应") < 浅露(hint) < 深谈(share)
    if score >= 0.50:
        level = "share"
    elif score >= 0.30:
        level = "hint"
    else:
        level = "avoid"
    return {"level": level, "score": score, "inv": inv, "trust": trust,
            "recip": recip, "fit": fit}


def generate_reply(person: Person, user_input: str,
                   history: list[dict] | None = None,
                   llm: Callable | None = None,
                   image_url: str | None = None) -> str:
    """生成回应。流程：
    1) 意图分类；2) 披露模型算等级；3) 检索相关记忆；
    4) 若 LLM 可用 → DeepSeek 生成（边界由披露等级决定）；
       否则 → 规则模板兜底。"""
    history = history or []
    intent = classify(user_input)
    related = retrieve_memories(person, intent, user_input) if intent == "ask_past" else []
    disc = evaluate_disclosure(person, intent, user_input, history)
    level = disc["level"]
    reaction = evaluate_reaction(person, user_input, history, intent)

    # LLM 优先（若可用）
    if llm is None and llm_available():
        llm_call = generate_reply_llm
    else:
        llm_call = llm

    if llm_call is not None:
        reply = llm_call(person=person, user_input=user_input, intent=intent,
                         related=related, can_reveal=related[:2],
                         disclosure=level, reaction=reaction, history=history,
                         image_url=image_url)
        if reply:
            # 甲：生成后校验 —— 若与她的事实库**明确矛盾**（编造），替换为合规回应
            if _conflicts_with_facts(reply, person):
                return _template_reply(person, intent, related, "avoid", user_input)
            return reply

    # 降级：规则模板（按披露等级）
    return _template_reply(person, intent, related, level, user_input)


# ── 甲(加强) ：生成后校验器（"完整事实序列化比对"—— LLM 只能断言事实库内容）──

def _facts_context(person: Person) -> dict:
    """提取事实库的关键断言（用于矛盾检测 + 允许集校验）。"""
    f = person.facts
    if f is None:
        return {}
    return {
        "siblings": f.siblings,
        "father_job": f.parents_job[0] if f.parents_job else "",
        "mother_job": f.parents_job[1] if len(f.parents_job) > 1 else "",
        "work": f.job,
        "city": f.current_city,
        "province": f.birth_place_province,
        "structure": f.family_structure,
        "edu": f.education_current,
        "school": f.school_type,
        "major": f.major,
        "residence": f.residence,
        "interests": list(f.interests),
        "keeps": f.keeps,
        "relationship": f.relationship_status,
        "context": f.to_context(),        # 完整事实清单（允许集）
    }


# 事实库的"负面断言"（她确定没有/没有的事；LLM 若确认"有"→编造）
# 这些是她事实库里没出现过、但 LLM 可能会"即兴确认有"的客观事实。
_NEGATIVE_ASSERTIONS: list[tuple[tuple[str, ...], str]] = [
    # （触发词（确认有），说明）
    (("养了猫", "养了狗", "养了只", "我有只猫", "我有只狗", "我养了", "我养一只"), "宠物"),
    (("我买了车", "我有一辆车", "我有辆车", "我开车的"), "车"),
    (("我买了个房子", "我有套房", "我自己的房子", "我买了房"), "房"),
    (("我去过欧洲", "我留学", "我出过国", "我留过学"), "海外经历"),
    (("我哥", "我弟", "我姐", "我妹", "哥哥", "弟弟", "姐姐", "妹妹"), "兄弟姐妹"),
]


def _assertions_fit_facts(reply: str, ctx: dict) -> bool:
    """完整事实序列化比对：回复中的"客观事实声明"是否都在事实库内。

    做法（务实、避免误伤）：
    - 正面：回复若提到"父母职业/工作/城市/学校/专业/住所/兴趣"类词，须与事实库一致（或含糊/不涉及）；
    - 负面：若回复出现"确认有（宠物/车/房/出国/兄弟姐妹）"而事实库对应为"无/不存在" → 编造。
    返回 True = 编造（应拦截）。
    """
    import re as _re

    # 1. 负面断言：确认"有"而事实无 → 编造
    if ctx["siblings"] == 0:
        for words, _label in _NEGATIVE_ASSERTIONS:
            if any(w in reply for w in words):
                return True

    # 2. 城市/省份不符（她出生/现居固定）
    if ctx["city"]:
        m = _re.search(r"(住在|家住|家是|我是|来自)([\u4e00-\u9fa5]{2,4})(市|省|人)", reply)
        if m and m.group(2) not in (ctx["city"], ctx["province"]):
            return True

    # 3. 单位/公司（事实无单位名：有"公司/事务所/集团"这类具体单位 → 编造）
    if _re.search(r"在\S{1,8}(公司|单位|事务所|工作室|集团|厂)", reply):
        return True

    # 4. 父母职业不一致（她说"我爸是医生"但事实是工程师）
    if ctx["father_job"]:
        for w in ("我爸", "我爸爸", "我爸是", "父亲"):
            if w in reply and ctx["father_job"] not in reply:
                return True
    return False


def _conflicts_with_facts(reply: str, person: Person) -> bool:
    """检测 LLM 回复是否**编造**（完整事实序列化比对 + 保守不误伤主观表达）。

    - 主观表达（我觉得/我记得/我不太清楚/也许）与含糊回应不拦；
    - 人生事实（有/没有、在哪、什么职业）必须在事实库内，否则编造。"""
    ctx = _facts_context(person)
    if not ctx:
        return False
    import re as _re

    # ── A. 明确矛盾（原有，快速路径）──
    # 兄弟姐妹：独生却说有
    if ctx["siblings"] == 0:
        for w in ("我哥", "我弟", "我姐", "我妹", "哥哥", "弟弟", "姐姐", "妹妹",
                  "有个哥", "有个弟", "有个姐", "有个妹"):
            if w in reply:
                return True
    # ── B. 完整事实序列化比对（升级：替代"编造专属词"白名单）──
    return _assertions_fit_facts(reply, ctx)


def _template_reply(person: Person, intent: str, related: list[Memory],
                    level: str, user_input: str = "") -> str:
    if intent == "greeting":
        return f"嗯，我在。{person.describe_current()}。你呢？"
    if intent == "ask_past":
        if level == "share" and related:
            m = related[0]
            return (f"{m.text}……我还记得这个。不是所有事都记得，"
                    f"但这件事，好像一直没过去。")
        if level == "hint" and related:
            return (f"嗯……{related[0].text}。具体的，以后再说吧。")
        # 兜底：家庭/关系话题（刚认识被问家人）→ 警觉/不舒服，而非平静带过
        if any(w in user_input for w in ("妈妈", "爸妈", "我爸", "家人", "家里", "室友", "朋友")):
            return "……怎么突然问这个？我们还不熟吧。"
        return "啊……过去的事啊，我不太想一下子全说出来。你为什么问这个？"
    if intent == "ask_now":
        return f"{person.describe_current()}，每天就是过日子。你呢，最近怎么样？"
    if intent == "ask_personal":
        return f"我叫{person.name}。至于别的嘛……你先说你叫什么？"
    if intent == "comfort":
        return "嗯……我可能不太会说安慰的话。但你要是想讲，我听着。"
    if intent == "user_share":
        # 你分享了自己 → 她回应（对等：真实人会因你这句敞开更愿意谈）
        return "……嗯。谢谢你告诉我这个。你愿意说这些，我也会记得的。"
    return "嗯……嗯。我话不多，但你说的话我听着的。"


def _record_story(person: Person, intent: str, user_input: str) -> None:
    """① 长期记忆沉淀：把这轮里"值得记住的时刻"写进她的故事（她记得的）。

    只记重要时刻（不记流水账）：你敞开心扉/她接住你的难受/你们有过的不愉快/你说的承诺。
    """
    if not user_input:
        return
    # 特殊时刻（长自我暴露）——与 apply_conversation_effects 的 special_moments 同源
    if intent == "user_share" and len(user_input) >= 20:
        person.record_chronicle("special", f"你那次跟她说：{user_input[:36]}{'…' if len(user_input) > 36 else ''}")
        return
    if intent in ("user_share", "comfort"):
        person.record_chronicle("share", f"你对她说：{user_input[:28]}{'…' if len(user_input) > 28 else ''}")
        return
    # 生气：她真的生气了（内敛的怒——不说太多，但她记得）
    if getattr(person, "is_angry", False) and person.angry_turns > 0:
        person.record_chronicle("anger", f"你们有过一次不愉快，她真的生气了——她没说太多，但她记得")
        return
    # 承诺：你说过的话（她这种人对"答应过"记得很牢）
    if any(w in user_input for w in ("一定", "答应", "保证", "下次一定", "我陪")):
        person.record_chronicle("promise", f"你答应过她：{user_input[:24]}{'…' if len(user_input) > 24 else ''}")


def apply_conversation_effects(person: Person, intent: str, reply_len: int,
                               user_input: str = "") -> None:
    """一次对话后：情绪/信任微变 + 记录相处（长期陪伴：累积推动关系阶段）
    + 你对她的关系影响（③被改变：温暖/伤害累积 → 写回认识）。"""
    v_shift = 0.02 if intent in ("greeting", "chat") else 0.0
    t_shift = 0.05 if intent in ("ask_past", "comfort") else 0.02
    person.apply_interaction(v_shift, t_shift)
    # 长期陪伴：记录一次相处；深聊（聊过去/你敞开心扉/特殊）累计深谈 + 特殊记忆
    is_deep = intent in ("ask_past", "comfort", "user_share")
    person.record_interaction(is_deep=is_deep)
    # 特殊时刻：若你说了很特别的（较长自我暴露），记为特殊记忆
    if intent == "user_share" and len(user_input) >= 20:
        person.special_moments.append({"event": user_input[:40]})
    # ③ 被改变：你的行为影响她（温暖/信任 → warmth；羞辱/伤害 → hurt）
    warmth = 0.0
    hurt = 0.0
    if intent in ("user_share", "comfort"):
        warmth += 0.5          # 你敞开心扉/关心她 → 温暖
    if intent in ("ask_past",) and person.relationship_stage() in ("熟悉", "亲近", "深入"):
        warmth += 0.3          # 你愿意了解她的过去 → 温暖（关系越深越强）
    # 冒犯/伤害（引用 reaction 的判断：无语/沉默常常因受伤）
    from .reaction import _ROUGH_WORDS, _UNCOMFORTABLE
    if any(w in user_input for w in _ROUGH_WORDS):
        hurt += 1.0
    if any(w in user_input for w in _UNCOMFORTABLE):
        hurt += 0.8
    person.affect_via_you(warmth=warmth, trust_gain=t_shift, hurt=hurt)
    # 依恋演化：温暖→安全感↑、依赖缓升；伤害→安全感↓；忽冷忽热（话题跳跃/冷漠）→ 不稳定
    stability = 0.0
    if intent in ("greeting",) and warmth == 0:
        stability = 0.2   # 只是客气寒暄、无温度 → 关系停滞（不稳定）
    if hurt > 0:
        stability += 0.5
    person.update_attachment(warmth=warmth, hurt=hurt, stability=stability, absence=0.0)
    # ① 你们的故事（重要时刻沉淀——她记得的不只是最近几句）
    try:
        _record_story(person, intent, user_input)
    except Exception:
        pass


def maybe_touch_on_you(person: Person, rng=None, llm: Callable | None = None) -> str | None:
    """特殊时刻（长期陪伴的温暖感）：她偶尔会主动提起你/想起你。

    只在她已记住你的事、且关系达到"熟悉"以上时发生；概率随关系阶段升高。
    有 LLM 时以其生成"想起你"的话（更自然）；否则模板兜底。"""
    import random as _random
    rng = rng or _random
    stage = person.relationship_stage()
    if stage in ("初识",):
        return None
    if not person.shared_memories:
        return None
    # 概率：熟悉 20%、亲近 35%、深入 50%（乘以依恋调制 touch_freq——焦虑型更常想起，回避型很少）
    p = {"熟悉": 0.20, "亲近": 0.35, "深入": 0.50}.get(stage, 0.0)
    try:
        p *= person.attachment_modulation().get("touch_freq", 1.0)
    except Exception:
        pass
    if rng.random() >= p:
        return None
    mem = person.shared_memories[0]["text"]
    # LLM 生成（更自然；失败回退模板）
    if llm is None and llm_available():
        try:
            from .llm import generate_reply_llm
            r = generate_reply_llm(
                person=person, user_input=f"（你此刻想起了对方。对方曾告诉你：{mem}）",
                intent="task_reminder", related=[], can_reveal=[],
                disclosure="avoid", reaction="sincere", history=[])
            if r:
                return r
        except Exception:
            pass
    # 模板兜底（多变式）
    openings = [
        f"对了……（想了想）你说过{mem}。不知道你现在怎么样了。",
        f"刚才忽然想到，你提过{mem}。",
        f"（停了一下）我一直没跟你说，其实你上次说的{mem}，我记着呢。",
        f"……你最近还在忙{mem}里说的那件事吗？",
    ]
    return rng.choice(openings)
