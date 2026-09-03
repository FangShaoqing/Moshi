"""相遇背景（meeting）—— 你们怎么认识的（**从她的人生经历里针对性生成**，不是模板）。

原则（协作方 2026-09-03 确认）：
- 她的人生已书写完毕；相遇是**她世界里发生的事**——"网友"：
  在一个属于她的角落（她的书/她的画/她的歌……）里，你们搭上了话；
- **针对性**：由种子 + 她的事实（兴趣/专业/性格）派生——爱看书的人认识在书评区，爱画画认识在画帖，
  爱听歌认识在歌的评论区，都不占就认识在她常去的树洞/论坛；
- 她记得这段：初始关系 = 熟悉（网上认识了一段时间，话不多但没断过）、信任基准 0.5——
  她不是"突然闯入的陌生人"，**她看着你，是'认识的人'**；
- **人生不许编**同样适用：背景是系统侧生成的事实（持久化），她只说这里写的东西，不即兴编细节。
"""

from __future__ import annotations

import random
from typing import Any


def _pick_scene(facts: Any) -> str:
    """兴趣/专业 → 她人生的哪个角落（针对性：她是什么样的人，就在哪里认识你）。"""
    interests = " ".join(getattr(facts, "interests", ()) or ())
    major = getattr(facts, "major", "") or ""
    if any(k in interests for k in ("看小说", "逛旧书店", "写点东西")) or "文学" in major:
        return "book"          # 书（她的书里）
    if any(k in interests for k in ("画画", "做手账")):
        return "art"           # 她的画/手账
    if "听歌" in interests or "音乐" in major:
        return "music"         # 歌的评论区
    return "forum"             # 她常去的树洞/论坛（兜底）


_SCENE_TEXT: dict[str, dict[str, str]] = {
    "book": {
        "place": "一本书的评论区",
        "spark": "她在那本书下留言，写了几句自己的想法（她很少评论的，那天不知道为什么写了）。"
                 "你回了她一句——不是敷衍的那种。她愣了一会儿，回了两句。",
        "thread": "后来你们偶尔聊起那本书、别的小说，还有她画的那些东西。每次都不长，"
                  "但她记得你说话的样子。",
    },
    "art": {
        "place": "她发画/做手账的地方",
        "spark": "她贴了一幅画（手账的一页）。你留了言，说得不像是客套——她看了两遍。"
                 "隔了一天，她回了一句。",
        "thread": "后来她偶尔发新东西，你会来看。你们聊画、聊她手账里的字，"
                  "每次都不长，但她记得你是那个会看的人。",
    },
    "music": {
        "place": "一首歌的评论区",
        "spark": "她在一首老歌下面说了一句话（像是对自己说的）。你回了她一句："
                 "'我也常听这首。'她没再回——但第二天她回复了你。",
        "thread": "后来你们偶尔聊歌、聊歌里的事。每次都不长，但她知道你是听的。",
    },
    "forum": {
        "place": "她常去的那个角落",
        "spark": "她发了条没什么人理的帖子，你回了。她没理你——后来有一天她突然回了：'你说得对。'",
        "thread": "后来偶尔碰到就聊几句。每次都不长，但从那以后，她认得你了。",
    },
}


def generate_meeting_story(seed: int, facts: Any) -> dict:
    """生成"你们怎么认识的"（确定性：种子+她的事实 → 同一个人永远是同一段）。"""
    scene = _pick_scene(facts)
    rng = random.Random(f"{seed}:meeting")
    text = _SCENE_TEXT[scene]
    duration = rng.choice(["半年多", "大半年", "快一年"])
    spark = rng.choice([text["spark"], text["spark"]])   # （确定性占位，保持结构统一）
    return {
        "scene": scene,
        "place": text["place"],
        "duration": duration,
        "spark": text["spark"],
        "thread": text["thread"],
        "qq_add": ("有一天你说：'加个QQ吧。'她想了一下，给了。"
                   "她认生，但她觉得你不一样——'这个人，可以聊下去。'"),
        "narrative": (
            f"你们认识有{duration}了。起点在{text['place']}：{text['spark']}"
            f"{text['thread']}后来你们加了QQ，继续说那些不长的话。"
            "她话少，但你说的话，她一直听着。"
        ),
    }


def story_context(story: dict | None) -> str:
    """给 LLM 的"你们认识的起点"（她记得的；这是真实发生在她世界里的）。"""
    if not story:
        return ""
    return (f"【你们认识的起点——这是真的，她记得】（{story.get('place', '')}，认识{story.get('duration', '')}了）\n"
            f"{story.get('narrative', '')}\n"
            "- 所以你们不是'刚认识的陌生人'：她认识你，你也认识她；她话少，但她认人。\n"
            "- 被问到'我们怎么认识的'，按上面的事实说（她记得），不要编别的细节；"
            "她不太会主动讲这些，被问到了才讲。\n")
