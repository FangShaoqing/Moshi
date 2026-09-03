"""天行数据（news）—— 她"偶尔知道世界发生了一点点事"（不是播报机器）。

设计（协作方 2026-09-03 定稿）：
- **她关心什么 = 她是**：新闻类型由她的事实（专业/职业/兴趣）**针对性**决定——
  软件工程/IT → 科技类词；学前/护理 → 教育/医疗类词；文科/编辑/书店 → 文化类词；
  会计/营销 → 财经民生类词；**任何人都 + 社会民生**（她的一天活在民生里）；
- 数据源：**综合新闻 generalnews**（一个接口全量）优先，社会新闻 social 保底；无需挨个申请；
- 克制：只留 **2 条**（1 条民生 + 1 条与她领域相关），6 小时缓存；
- 不播报：提示词明示"你可能知道，也可能不在意；不会主动播报"；
- 人生不许编：内容来自接口，她只说给定条目/自己的感受。

未来任何种子（程序员/护士/记者……）都不需要为新领域再申请接口——打分表自动适配。
"""

from __future__ import annotations

import gzip
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_KEY_FILE = _ROOT / "config" / "secrets.json"
_CACHE_FILE = _ROOT / "data" / "news_cache.json"

API = "https://apis.tianapi.com"
SOURCES = ("generalnews", "social")      # 综合新闻优先；社会新闻保底
KEEP = 2                                 # 只留 2 条
TTL = 6 * 3600                           # 6 小时缓存
POOL = 50                                # 每次取前 N 条做现场打分


def news_key() -> str:
    env = os.environ.get("NEWS_API_KEY", "").strip()
    if env:
        return env
    try:
        if _KEY_FILE.exists():
            v = (json.loads(_KEY_FILE.read_text(encoding="utf-8")).get("NEWS_API_KEY") or "").strip()
            if v and not v.startswith("在此"):
                return v
    except Exception:
        pass
    return ""


# ── 领域关键词表（她是什么人 → 她可能留意的界面）──
DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "tech": ("编程", "软件", "IT", "互联网", "程序员", "科技", "代码", "AI", "人工智能",
             "芯片", "手机", "电脑", "机器人", "数据", "算法", "数码"),
    "edu": ("教育", "学校", "老师", "学生", "高校", "考研", "幼儿园", "中小学", "招生", "学位"),
    "medical": ("医疗", "医院", "医生", "护士", "健康", "医保", "药", "疾病", "养老"),
    "culture": ("文化", "图书", "出版", "书店", "展览", "电影", "文学", "博物馆",
                "作者", "读书", "艺术", "播客"),
    "finance": ("财经", "经济", "股市", "基金", "房价", "消费", "物价", "工资",
                "就业", "租金", "通胀", "补贴"),
    "society": ("民生", "地铁", "公交", "菜价", "天气", "交通", "社区", "外卖",
                "搬迁", "社保", "居民"),
}

_DOMAIN_RULES: list[tuple[tuple[str, ...], str]] = [
    # （触发词（事实里的专业/职业/兴趣），领域）
    (("软件工程", "程序", "IT", "计算机", "互联网", "运营", "新媒体"), "tech"),
    (("学前", "教育", "师范", "护理", "健康", "医学"), "edu"),
    (("护", "医护", "药学", "医院", "卫生"), "medical"),
    (("汉语言", "新闻传播", "编辑", "文案", "文学", "设计", "平面", "书店", "写"), "culture"),
    (("会计", "财务", "金融", "营销", "市场", "行政", "电商"), "finance"),
]


def her_domains(facts) -> tuple[str, ...]:
    """她的事实 → 她关心的领域（针对性：她是什么人，就关心什么界面）。"""
    text = " ".join([
        getattr(facts, "major", "") or "",
        getattr(facts, "job", "") or "",
        " ".join(getattr(facts, "interests", ()) or ()),
    ])
    got: list[str] = []
    for triggers, domain in _DOMAIN_RULES:
        if any(t in text for t in triggers) and domain not in got:
            got.append(domain)
    if not got:
        return ("culture",)          # 兜底：她是个安静的看书女孩（任一种子都有文化底色）
    return tuple(got)


def _score(title: str, domains: tuple[str, ...]) -> int:
    """和她的关系分：领域词 +2，社会民生 +1（社会民生是通用通道，不作为领域重复计分）。"""
    s = 0
    for d in domains:
        if d == "society":
            continue                        # 通用通道，下面统一 +1
        if any(k in title for k in DOMAIN_KEYWORDS.get(d, ())):
            s += 2
    if any(k in title for k in DOMAIN_KEYWORDS["society"]):
        s += 1
    return s


def _fetch(cat: str) -> list[dict]:
    key = news_key()
    if not key:
        return []
    url = f"{API}/{cat}/index?key={key}&num={POOL}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "moshi/selfuse"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
            d = json.loads(raw.decode("utf-8"))
        if d.get("code") == 200:
            return (d.get("result") or {}).get("newslist", []) or []
    except Exception:
        pass
    return []


def _load_cache() -> dict:
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(c: dict) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _pool() -> list[dict]:
    """资源池（缓存 6h；综合新闻优先，社会新闻保底）。"""
    cache = _load_cache()
    hit = cache.get("pool", {})
    if hit.get("t") and time.time() - hit["t"] < TTL:
        return hit.get("items", [])
    items: list[dict] = []
    seen = set()
    for cat in SOURCES:
        for n in _fetch(cat):
            title = (n.get("title") or "").strip()
            if title and title not in seen:
                seen.add(title)
                items.append({"title": title, "source": (n.get("source") or "").strip()})
        if items:
            break                       # 第一个有数据的源就够了
    _save_cache(_load_cache() | {"pool": {"t": time.time(), "items": items}})
    return items


def news_interest(person) -> float:
    """她对新闻的关心程度（0~1）——**从她的人格里长出来**，不是写死。

    信号（确定性，种子派生）：
    - 职业/专业（做媒体的她天然关注）；兴趣（文化/书/画的她偏文化）；
    - 信任底色（"怕再一次错付"的她对世界保持距离 → 少看）；
    - 缺点（会为以后焦虑 → 多瞄两眼就业/民生；心里有事不说 → 更少看）；
    - 心情（日子紧/倦怠 → 当天不想看，由 _want_news 处理）。
    """
    base = 0.30                                   # 一般人的底子：有一搭没一搭地看
    facts = getattr(person, "facts", None)
    if facts is not None:
        text = " ".join([
            getattr(facts, "major", "") or "",
            getattr(facts, "job", "") or "",
            " ".join(getattr(facts, "interests", ()) or ()),
        ])
        if any(t in text for t in ("新闻传播", "记者", "媒体", "编辑", "新媒体")):
            base = 0.75                           # 媒体人：她的工作就是看新闻
        elif any(t in text for t in ("汉语言", "文学", "书店", "写", "设计", "平面", "文化")):
            base = 0.45
        elif any(t in text for t in ("软件", "计算机", "运营", "电商", "科技")):
            base = 0.40
        elif any(t in text for t in ("会计", "财务", "行政", "营销", "护理", "教育")):
            base = 0.35
    # 信任底色：对外界留一手 → 少看（她不是好凑热闹的人）
    for b in getattr(person, "beliefs", []) or []:
        t = getattr(b, "tendency", "") or ""
        if any(k in t for k in ("留一手", "怕再一次", "不敢", "不信")):
            base -= 0.12
        if any(k in t for k in ("想看看外面", "好奇")):
            base += 0.10
    # 缺点：为以后焦虑 → 民生/就业多看一点；心里有事不说 → 更少看
    for fl in getattr(person, "flaws", []) or []:
        if "焦虑" in fl or "想太多" in fl:
            base += 0.10
        if "不说" in fl or "藏" in fl:
            base -= 0.05
    return max(0.08, min(0.9, base))


def _want_news(person, day: int) -> bool:
    """今天她看新闻吗？——兴趣 × 心情，按"每天"掷一次（确定性）。"""
    i = news_interest(person)
    mood = getattr(person, "life_mood", "") or ""
    if any(k in mood for k in ("烦", "累", "提不起劲")):
        i *= 0.6                                  # 日子紧：连新闻都不想打开
    if getattr(person, "exhausted", False):
        return False                              # 倦怠：不看
    import random as _random
    rng = _random.Random(f"{getattr(person, 'seed', 0)}:news:{day}")
    return rng.random() < i


def today_news(facts=None, person=None, day: int | None = None) -> list[dict]:
    """她可能留意的新闻。person 存在时：**她想看才看**（兴趣×心情，每天一决定）——没想看的今天她不知道新闻。

    返回最多 2 条（领域优先，民生补位；与她无关的不留）。
    """
    if person is not None:
        try:
            from .v4 import timeline as _tl
            d = day if day is not None else _tl.life_day_of(getattr(person, "birth_date", None))
            if not _want_news(person, d):
                return []                         # 她今天没看（真实：不是所有人都看新闻）
        except Exception:
            pass
    domains = her_domains(facts)
    scored = sorted(((_score(it["title"], domains), it) for it in _pool()),
                    key=lambda x: -x[0])
    picked: list[dict] = []
    for sc, it in scored:
        if sc <= 0:
            break                                 # 与她无关的不留
        if not any(p["title"] == it["title"] for p in picked):
            picked.append(it)
        if len(picked) >= KEEP:
            break
    return picked[:KEEP]


def news_note(facts=None, person=None) -> str:
    """一句话给 LLM（克制版）：她想看才看；今天没看就是没看（空）。"""
    items = today_news(facts, person=person)
    if not items:
        return ""
    marks = ("①", "②")
    lines = [f"{marks[i if i < 2 else 1]} {it['title']}" for i, it in enumerate(items[:2])]
    return "这个世界今天发生了一些事：" + "  ".join(lines) + "。"
