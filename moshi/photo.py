"""照片决策（photo）—— 她想不想发、发什么：**她的心情和日子做主**（不是定时任务）。

原则（协作方 2026-09-02）：
- 频率看她的心情：想发才发（关系/依恋/心情/日子基调参与概率）；生气不发；倦怠/低落可能发"没心情"照；
- **照片 = 她日子的呈现**（加班夜景/下雨檐下/旧书店/楼下猫/深夜桌面…），不是摆拍；
- 真实的不完美：可以是空桌子、糊的、暗的——她不会天天阳光明媚；
- 确定性：同条件同选择（盐=种子×相处次数×日子基调），可复现。

场景提示词由她的日子（life_log 最近事件）+ 形象卡（事实层）合成。
"""

from __future__ import annotations

import random
from pathlib import Path

from . import img_gen

# ── 她的形象卡（与 facts 一致：素净、普通、耐看；生图把"她"锚定住）──
HER_LOOK = ("二十出头的中国女大学生，普通但耐看，及肩的黑发没怎么打理，"
            "素净的脸，没化妆，穿白色T恤和素色外套，安静的样子")
PHOTO_STYLE = ("手机随手拍的真实照片，日常光线，自然不摆拍，写实，生活感，"
               "稍微有点活着的粗糙（暗角/轻微模糊都可以），不是广告大片")
NEGATIVE = ("网红脸，精致，精修，AI塑料感，过度美白，摆拍，影楼，水印，"
            "多余手指，畸形，模糊，低质量文本")

# ── 场景池：她日子里的事 → 画面（有她、有生活）──
SCENES: dict[str, tuple[str, str]] = {
    "night_street": ("夜晚的城市街道，昏黄路灯，她站在路边等车，低头看手机，"
                     "白T外面套了件外套，神情平淡，光线暖黄"),
    "bookstore":    ("旧书店里，木书架，暖黄灯光，她蹲在书架前翻一本旧书，侧脸安静"),
    "cat":          ("楼道门口，一只橘猫蹲在那里，她蹲下来看着它，嘴角有点弧度，白T"),
    "rain_eave":    ("下雨天，她站在屋檐下躲雨，肩膀头发有点湿，看着雨幕，安静"),
    "night_desk":   ("深夜的桌面：一碗泡面，一双筷子，手机亮着，热气，台灯下，她的一只手在镜头里"),
    "window_book":  ("宿舍窗边，下午的光照进来，她坐在椅子上看书，窗外有点绿，安静"),
    "dorm_door":    ("宿舍楼门口傍晚，她拎着一袋东西走回来，路灯刚亮，背影"),
    "morning_bus":  ("早晨的公交站台，她夹着书站着，头发有点乱，没睡醒的样子"),
    "market":       ("菜市场里，她在挑青菜，挽着袋子，人声喧闹但她安静，阳光侧照"),
    "lonely_desk":  ("一张空桌子：一杯凉了的水，摊开的笔记本，窗外暗下来——她没在，"
                     "或者说她不想被拍"),
}

# 日子关键词 → 场景（她的日子说什么，照片就长什么）
_DAY_TO_SCENE = [
    ("加班", "night_street"), ("忙", "night_street"), ("晚", "night_street"),
    ("旧书店", "bookstore"), ("书", "window_book"),
    ("橘猫", "cat"), ("猫", "cat"),
    ("雨", "rain_eave"), ("下雨", "rain_eave"),
    ("煮面", "night_desk"), ("饭", "night_desk"),
    ("醒了", "morning_bus"), ("没睡好", "morning_bus"),
    ("买菜", "market"), ("超市", "market"),
]


def scene_keys_from_life(person) -> list[str]:
    """她的最近的日子的文字 → 命中场景（按顺序；可能多个）。"""
    keys = []
    log = getattr(person, "life_log", []) or []
    mood = getattr(person, "life_mood", "") or ""
    text = " ".join(str(e.get("text", "")) for e in log[-5:]) + " " + mood
    for kw, scene in _DAY_TO_SCENE:
        if kw in text and scene not in keys:
            keys.append(scene)
    return keys or ["window_book"]


def _mood_factor(person) -> float:
    """她的心情对"发照片"的影响：低落/倦 → 更少发，但可能发'没心情照'。"""
    mood = getattr(person, "life_mood", "") or ""
    if any(k in mood for k in ("烦", "累", "提不起劲")):
        return 0.35
    return 1.0


def decide_photo(person, day: int | None = None) -> dict | None:
    """这一轮她想发照片吗？→ {"scene": 场景key, "prompt": 完整提示词} 或 None。

    规则（像她，不是定时器）：
    - 生气 → 不发（冷处理的对象不配看照片）；
    - 依恋越深（touch_freq）、关系越亲近 → 越想给你看她的世界；
    - 日子紧（烦/累）→ 大概率不发；若发，发'空桌子'（真实的不完美）；
    - 倦怠/低谷 → 可能有"没心情照"。
    决定按"每天"取一次（盐=种子×相处次数×今天——她想不想给你看她的世界，定了就定了）。
    """
    if getattr(person, "is_angry", False):
        return None
    if getattr(person, "exhausted", False):
        return None
    try:
        stage = person.relationship_stage()
        freq = person.attachment_modulation().get("touch_freq", 1.0)
    except Exception:
        stage, freq = "初识", 1.0
    base = {"初识": 0.05, "熟悉": 0.10, "亲近": 0.16, "深入": 0.22}.get(stage, 0.08)
    p = max(0.02, min(0.5, base * freq * _mood_factor(person)))
    try:
        n = int(getattr(person, "interaction_count", 0) or 0)
    except Exception:
        n = 0
    if day is None:
        try:
            from .v4 import timeline as _tl
            day = _tl.life_day_of(person.birth_date)
        except Exception:
            day = 0
    rng = random.Random(f"{getattr(person, 'seed', 0)}:photo:{n}:{day}")
    if rng.random() >= p:
        return None
    # 场景：日子说了算；日子闷 → 空桌子（真实的不完美）
    scenes = scene_keys_from_life(person)
    if any(k in (getattr(person, "life_mood", "") or "") for k in ("烦", "累", "提不起劲")):
        scenes = ["lonely_desk"]
    scene = rng.choice(scenes)
    body = SCENES.get(scene, SCENES["window_book"])[0]
    prompt = f"{HER_LOOK}。{body}。{PHOTO_STYLE}"
    return {"scene": scene, "prompt": prompt, "negative": NEGATIVE}


def make_photo(person, seed: int | None = None) -> tuple[Path, dict] | None:
    """生成她今天想给你看的照片 → (图片路径, 决策)；失败/没准备好 → None。"""
    dec = decide_photo(person, seed)
    if dec is None:
        return None
    base = img_gen.base_image()
    if base is None:
        return None                       # 本体图未就绪（等用户放 her_base.png）
    s = seed if seed is not None else random.Random(f"{getattr(person, 'seed', 0)}:{dec['scene']}").randint(0, 2 ** 31)
    try:
        out = img_gen.img2img(base, dec["prompt"], dec["negative"],
                              strength=0.55, seed=s)
        return out, dec
    except Exception as e:
        print(f"[photo] 生成失败：{e}")
        return None
