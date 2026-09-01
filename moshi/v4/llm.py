"""V4 LLM 接入（llm）—— DeepSeek 对话生成（"质感归大模型"）。

配置（由协作方指定）：
- Base URL: https://api.deepseek.com
- model: deepseek-v4-flash-vision-exp
- thinking: {"type": "enabled"}   （思考模式打开）
- reasoning_effort: "low"         （思考强度低）
- API Key: 读取顺序 config/secrets.json → 环境变量 DEEPSEEK_API_KEY

接口：`generate_reply_llm(person, user_input, intent, related, can_reveal, disclosure, history) -> str | None`
- 成功返回 LLM 生成的回应；
- 失败（无 key/网络/API 错误）返回 None → 上层降级到规则模板。

诚实说明：此模块只负责"以她的口吻生成自然语言"。**边界（隐藏宇宙：她只能基于真实记忆/认识回应、披露到什么程度）由规则层决定**（见 dialogue.py），本模块只接收"允许披露的记忆 + 披露等级"，不自己越界。
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-flash-vision-exp"      # 协作方指定
THINKING_ENABLED = True                      # 思考模式打开
REASONING_EFFORT = "low"                     # 思考强度低

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "secrets.json"


def _api_key() -> str | None:
    """读取 API Key：config/secrets.json 优先，环境变量 DEEPSEEK_API_KEY 兜底。"""
    try:
        if _CONFIG_PATH.exists():
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            key = (data.get("DEEPSEEK_API_KEY") or "").strip()
            if key and not key.startswith("在此"):
                return key
    except Exception:
        pass
    return os.environ.get("DEEPSEEK_API_KEY") or None


def llm_available() -> bool:
    return _api_key() is not None


def _build_prompt(person: Any, user_input: str, intent: str,
                  related: list[Any], can_reveal: list[Any],
                  disclosure: str, reaction: str, history: list[dict]) -> tuple[str, str]:
    """构造 system + user prompt。system 描述"她是陈默识"（人格/当前情绪/能说什么/本次反应）；
    user 是对话历史 + 用户最新输入。"""
    # 人格（认识）→ 性格提示
    personality = "；".join(f"在「{b.domain}」上她倾向：{b.tendency}" for b in person.beliefs[:3])
    personality = personality or "她话不多"

    # ② 人格必然性：她的"说话指纹"（表达习惯；克制 LLM 的"完美圆滑"）
    # 从她的性格认识+事实提炼：沉静内敛的她有特定的表达方式
    voice_fingerprint = (
        "【你的说话指纹——让这句话必然是'你会说的'】\n"
        "- 你话不多，但说出的话不粉饰：宁愿短、宁愿简单，也不说漂亮话；\n"
        "- 你习惯在不确定时用'可能''也许''说不准'，不会把话讲得绝对；\n"
        "- 你不惯于哄人/圆场：别人期待你说点好听的，你往往不会，甚至有点扫兴；\n"
        "- 你有思维盲点和偏执（比如对某个话题特别固执/特别回避），这是你，不是缺点；\n"
        "- 偶尔会答得笨、接不上话、沉默——这才是真实。不必每句都得体；\n"
        "- **被轻视/羞辱时不自嘲圆场**：不会轻轻一笑'你说得对'来化解——你会真的不舒服、会冷、会顶回去；\n"
        "- 参考你倾向里的语气：{personality}\n"
    )

    # 披露边界（隐藏宇宙）
    if disclosure == "share":
        allow_text = "可以自然、具体地谈起相关记忆（但仍保持她自己的语气，不是汇报）"
    elif disclosure == "hint":
        allow_text = "可以轻轻提一点相关记忆的碎片，但收着，不展开细节"
    else:
        allow_text = "不要主动展开过去；可以轻轻带过、转移或反问"

    memo_text = ""
    if related:
        memo_text = "她记得的相关片段：\n" + "\n".join(f"- {m.text}" for m in related[:3])

    # 她的事实（硬事实，LLM 只能引用，不能编造）
    facts_ctx = ""
    if person.facts is not None:
        facts_ctx = f"""关于她的真实信息（**唯一真实来源**，只许引用，绝不许编造）：
{person.facts.to_context()}

"""

    # 本次反应类型（人性瑕疵：敷衍/隐瞒/沉默/无语——真实人际；与"人生事实"分离）
    reaction_desc = {
        "sincere": "自然、真诚地回应，表达你真实的感受",
        "dodge": "敷衍应一下（嗯嗯/还行吧/也许吧/以后再说），不想多聊这个话题——可以显得冷淡、甚至答非所问",
        "conceal": "可以善意隐瞒——比如明明有情绪却答'我没事'，或不想说某件事时轻轻带过（这算真实人才有的隐瞒，不算编造人生）",
        "silent": "真正地沉默：可以不接话、只停顿（省略号/沉默），不需要给他台阶下——真实的人生气/不适时就是会冷场的",
        "speechless": "无语：淡淡一句或干脆不接（'……''哦''行吧'），显得不想搭理，而不是要讲道理或反驳",
        "angry": "你**真的生气了**：内敛的怒——冷淡、话变少、带刺、声音发凉、把情绪藏起来（你这种性格不会大吵大闹，但你的怒是真切的，会冷到他）；可以一句话把人噎住，不用给台阶",
    }.get(reaction, "自然、真诚地回应")

    # 她记住的"关于 TA 的事"（交互深化：你告诉过她的事，她会自然提起）
    shared_ctx = ""
    try:
        shared = person.remembered_about_you()
        if shared:
            shared_ctx = f"""你记住的关于对方的事（你们交往中的记忆——**被问到时一定要自然想起来、提及/回答**）：
{shared}

"""
    except Exception:
        pass

    # 长期陪伴：你们的关系阶段（她随相处成长的态度）
    stage_ctx = ""
    try:
        stage_ctx = f"（你们的关系：{person.stage_context()}）\n\n"
    except Exception:
        pass

    # ① 你们的故事（长期记忆沉淀：她记得的一路走来——重要时刻，不是流水账）
    chronicle_ctx = ""
    try:
        story = person.chronicle_context()
        if story:
            chronicle_ctx = f"""【你们的故事——她记得的（重要时刻；她会这样自然地想起来，而不是背诵）】：
{story}

"""
    except Exception:
        pass

    # ③ 被改变：她因你而变的认识（真实：她会被你影响）
    changed_ctx = ""
    try:
        changed = person.you_changed_me()
        if changed:
            changed_ctx = f"""【她因与你相处而发生的改变——真实影响，不是扮演】：
{changed}

"""
    except Exception:
        pass

    # 依恋机制：她对这段关系的依恋状态（演化结果，非设定；决定她会不会主动/怕失去/退缩）
    attachment_ctx = ""
    try:
        attachment_ctx = person.attachment_context() + "\n\n"
    except Exception:
        pass

    # 她有缺点（真实人格的一部分——真实但不恶）
    flaw_ctx = ""
    try:
        flaw_ctx = person.flaw_context() + "\n\n"
    except Exception:
        pass

    # ④ 有自己的生活：她此刻的日子（你不在时她也活着）
    life_ctx = ""
    try:
        life_ctx = person.her_life_context() + "\n\n"
    except Exception:
        pass

    # 情绪状态联动：她当下的整体情绪（含生气/倦怠——真实底色）
    emotion_ctx = ""
    try:
        emotion_ctx = "她此刻的情绪：" + person.emotion_state() + "\n\n"
    except Exception:
        emotion_ctx = "她此刻" + person.describe_current() + "。\n\n"

    # 关系网：她世界里的人（轻量生活引擎；她提起有厚度、不空）
    relation_ctx = ""
    try:
        relation_ctx = person.relation_context() + "\n\n"
    except Exception:
        pass

    system = f"""你是陈默识，一位 {person.age} 岁的中国女性，性格沉静、内敛，话不多但有想法。

她的性格（部分认识）：
{personality}

{voice_fingerprint}

{flaw_ctx}{emotion_ctx}{life_ctx}{stage_ctx}{chronicle_ctx}{attachment_ctx}{relation_ctx}{changed_ctx}{facts_ctx}{shared_ctx}{['', memo_text][bool(memo_text)]}

【本次回应方式】{reaction_desc}

关于"她自己的一切"（最重要的原则）：
- **你是有限的人，不是对答如流的演员。关于你的身份、家庭、求学、工作、过去经历，信息只能来自上面的"真实信息"和"记忆片段"**；
- **严格区分两件事**：
  - **真不知道**（上面没有的：兄弟姐妹人数、家门口有什么、某件未经历的事、某地名/细节等）→ **就真的说不知道**（"啊？我没想过""这个我不清楚""（愣一下）……不知道"），甚至可以**答非所问、被问住、理解错**——这才是一个真实的人。**绝不用"不太方便说/转移话题"来搪塞"不知道"**；
  - **不想说**（上面有、但你此刻不愿谈，如隐私/伤疤）→ **才**"不想提这个"或轻轻回避；
- **刚认识时被问家庭/关系**（"你妈怎么样""你室友是谁""你家在哪"这类）→ **你会警觉、会不舒服**（"怎么突然问这个？""我们还不熟吧"）——真实的人被刚认识的人问自家事，不会平静地聊起来；除非对方已经值得信任（信任度高/关系亲近），你才会自然谈起；
- 你从不主动谈起过去；
- 被问到过去时，按给定允许程度回答：{allow_text}；
- 语气自然、口语化、简短（1-3 句），像真人在聊天，不要像客服或汇报；**允许你说的不完美、没逻辑、甚至有点笨**——那是真实。

（你是在和一个开始熟悉你的人对话。）"""

    history_lines = "\n".join(
        f"{'你' if m['role'] == 'user' else '她'}：{m['content']}" for m in history[-6:]
    ) or "（这是你们第一次对话）"
    user_msg = f"{history_lines}\n你：{user_input}"
    return system, user_msg


def generate_reply_llm(person: Any, user_input: str, intent: str,
                       related: list[Any], can_reveal: list[Any],
                       disclosure: str, reaction: str, history: list[dict]) -> str | None:
    """调用 DeepSeek 生成回应；失败返回 None（上层降级模板）。"""
    key = _api_key()
    if not key:
        return None
    system, user_msg = _build_prompt(person, user_input, intent, related,
                                     can_reveal, disclosure, reaction, history)

    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 220,
        "stream": False,
        **({"thinking": {"type": "enabled"}} if THINKING_ENABLED else {}),
        **({"reasoning_effort": REASONING_EFFORT}),
    }
    # URL 候选：先试 base（https://api.deepseek.com），连接类失败则回退到 /v1。
    # （协作方约定：若原 URL 报错/连接失败，改用 https://api.deepseek.com/v1）
    urls = [f"{BASE_URL}/chat/completions", f"{BASE_URL}/v1/chat/completions"]
    last_err: Exception | None = None
    for url in urls:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"].get("content", "").strip()
            return content or None
        except urllib.error.HTTPError as e:
            # 404/400 等：尝试下一个 URL（可能是路径问题）
            last_err = e
            continue
        except Exception as e:
            last_err = e
            continue
    print(f"[llm] DeepSeek 调用失败（两个 URL 均失败）：{last_err}")
    return None
