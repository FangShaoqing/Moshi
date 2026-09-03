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

# ── 她的形象卡（背影/侧影/局部才需要：长发、白T、素净）──
HER_SILHOUETTE = ("能看到一个穿白色T恤、及肩黑发的年轻女孩的背影或侧影，素净普通不打扮")
PHOTO_STYLE = ("candid phone photo, natural light, real life, shot on a phone, "
               "slightly imperfect, amateur framing, not staged, not advertising")
NEGATIVE = ("people, woman, girl, human face, selfie, influencer face, doll face, big eyes, "
            "heavy makeup, retouched, airbrushed, AI plastic, anime, cartoon, watermark, "
            "extra fingers, deformed, blurry, text, logo, dress, bow, uniform, "
            "nude, lingerie, underwear, cleavage, NSFW, sexualized, beach portrait")

# ── 场景池：她日子里的事 → 画面（**她的视角**：她给你看的是她看见的世界——没有人，没有自拍）──
# 写法关键（实测）：关键词式英文 + 无人物（负面压 people/girl）+ CFG≈7 —— 服从度完美
SCENES: dict[str, tuple[str, str]] = {
    "night_street": ("night city street under warm streetlights, empty sidewalk, wet asphalt, "
                     "a bus stop in the distance, cold night, phone photo, quiet"),
    "bookstore":    ("old bookshop interior, wooden shelves full of used books, warm light, "
                     "a close-up of books, first-person view, phone photo"),
    "cat":          ("orange stray cat sitting on concrete steps, doorway, chubby slightly dirty cat, "
                     "low angle phone photo, casual, natural light"),
    "rain_eave":    ("rain falling from an eave, wet street, a hand reaching out into the rain, "
                     "close-up, moody, phone photo"),
    "night_desk":   ("close-up photo of instant noodles in a bowl on a desk at night, steam rising, "
                     "chopsticks, warm desk lamp, glowing phone, open book, cozy"),
    "window_book":  ("open book on a windowsill, afternoon light, green leaves outside, "
                     "a mug, phone photo, calm"),
    "dorm_door":    ("evening dormitory building entrance, streetlamp just on, a bike parked, "
                     "empty stairs, warm light, phone photo"),
    "morning_bus":  ("morning bus stop, first light, empty bench, reflections in the bus window, "
                     "mist, phone photo, sleepy quiet"),
    "market":       ("wet market stall, fresh greens in woven baskets, sunlight from the side, "
                     "a hand picking vegetables, busy background, phone photo"),
    "lonely_desk":  ("empty desk: a glass of cold water, open notebook, window darkening outside, "
                     "quiet and a little lonely, phone photo"),
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
    prompt = f"{body}。{PHOTO_STYLE}"
    return {"scene": scene, "prompt": prompt, "negative": NEGATIVE}


def _has_person(path: Path) -> bool:
    """人像哨兵：DeepSeek vision 看一眼"照片里有没有人"。避免底模漏进路人/人物。"""
    try:
        import base64, json, urllib.request
        from .v4.llm import _api_key
        key = _api_key()
        if not key:
            return False          # 没有密钥就不拦（降级：照发）
        b64 = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        payload = {
            "model": "deepseek-v4-flash-vision-exp",
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "这张照片里有没有人（包括路人/背影/侧影/手以外的人体部位）？"
                                          "只回答一个字：有 或 没有"},
                {"type": "image_url", "image_url": {"url": b64}},
            ]}],
        }
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST")
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read().decode("utf-8"))
        ans = d["choices"][0]["message"]["content"]
        return "有" in ans and "没有" not in ans
    except Exception:
        return False


def make_photo(person, seed: int | None = None) -> tuple[Path, dict] | None:
    """生成她今天想给你看的照片 → (图片路径, 决策)；失败/没准备好 → None。

    现在用 txt2img（她的视角照片：世界/静物——不需要本体图）；
    生成后经"人像哨兵"检查，有人就换种子重来（最多 3 次）。
    """
    dec = decide_photo(person, seed)
    if dec is None:
        return None
    rng = random.Random(f"{getattr(person, 'seed', 0)}:{dec['scene']}")
    for _ in range(3):
        s = seed if seed is not None else rng.randint(0, 2 ** 31)
        try:
            # 配方（压力测试 10/10 稳定验证）：英文关键词 + still life + CFG7 + 无人物负面
            prompt = dec["prompt"] + ", still life"
            out = img_gen.txt2img(prompt, dec["negative"], seed=s)
            if not _has_person(out):
                return out, dec
            print(f"[photo] 有路人侵入，换种子重试（{s}）…")
        except Exception as e:
            print(f"[photo] 生成失败：{e}")
            return None
    return None
