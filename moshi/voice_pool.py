"""主动语音库（voice_pool）—— 她主动找你时"只会说那几句"（她话少，这很真实）。

原理：固定话 + 锁种子的 CosyVoice v2 声线（用户选定后锁死）→ 预合成文件
（data/voice_cache/pool_<key>_s<seed>.mp3）→ 主动时**直接发文件，零合成等待**。

用法：
- pick_pool_voice(person)：按她的心情/日子选一句（None=今天她不想说语音）；
- MANIFEST：句子登记表（key/text/seed/file/情绪标签）——用户逐句挑选后填种子。
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CACHE = _ROOT / "data" / "voice_cache"

# ── 话池登记表（key: 句子场景；seed: 用户挑中的种子；mp3/silk: 锁定的合成文件；feel: 心情标签）──
# 定稿（协作方 2026-09-04）：就用 pool_s1_s102（v2 声线·种子 102·speed 0.78·句间[breath]）
MANIFEST: dict[str, dict] = {
    "check": {"text": "嗯……今天忙完了没有？", "seed": 102,
              "mp3": str(_CACHE / "pool_s1_s102.mp3"),
              "silk": str(_CACHE / "pool_s1_s102_02header.silk"),
              "feel": "日常问候"},
}

# 挑句顺序（按"她当下的心情/日子"逐级匹配）
_RULES = [
    ("rain", False),    # 下雨的日子
    ("low", False),     # 她低落/失眠
    ("miss", False),    # 很想你
    ("check", True),    # 默认问候
]


def pool_file(entry: dict) -> Path | None:
    """锁定句子的发送文件（优先 QQ 可直接发的 silk；未生成回退 None）。"""
    for key in ("silk", "mp3"):
        f = entry.get(key)
        if f and Path(f).exists():
            return Path(f)
    return None


def _KEY_OF(entry: dict) -> str:
    for k, v in MANIFEST.items():
        if v is entry:
            return k
    return ""


def pick_pool_voice(person) -> tuple[Path, str] | None:
    """她此刻该说哪句？（若今天某人心情不合适 → None。规则按 lib 顺序试）"""
    mood = (getattr(person, "life_mood", "") or "")
    log = " ".join(str(e.get("text", "")) for e in (getattr(person, "life_log", []) or [])[-5:])
    from . import knowledge as _k
    rain_today = False
    try:
        today = _k.today_note()
        rain_today = any(k in today for k in ("雨", "雨水")) or any(k in log for k in ("雨",))
    except Exception:
        pass
    low = any(k in mood for k in ("烦", "累", "提不起劲", "失眠", "睡不着"))
    miss = getattr(person, "attachment_style", lambda: "")() in ("焦虑型", "安全型") \
           or float(getattr(person, "dependence", 0) or 0) > 0.5
    for key, need in (("rain", rain_today), ("low", low), ("miss", miss), ("check", True)):
        if key in MANIFEST and need:
            f = pool_file(MANIFEST[key])
            if f:
                return f, MANIFEST[key]["text"]
    # 兜底：任何一句都行（取第一句已锁定的）
    for e in MANIFEST.values():
        f = pool_file(e)
        if f:
            return f, e["text"]
    return None
