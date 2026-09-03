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


def today_news(facts=None) -> list[dict]:
    """她可能留意的新闻（2 条：最高分的民生/领域各一条；与她的世界相关优先）。"""
    domains = her_domains(facts)
    scored = sorted(((_score(it["title"], domains), it) for it in _pool()),
                    key=lambda x: -x[0])
    picked: list[dict] = []
    for sc, it in scored:
        if sc <= 0:
            break                       # 与她无关的不留
        if not any(p["title"] == it["title"] for p in picked):
            picked.append(it)
        if len(picked) >= KEEP:
            break
    return picked[:KEEP]


def news_note(facts=None) -> str:
    """一句话给 LLM（克制版）：'这个世界今天发生了一些事：①…；②…'——她可能知道也可能不在意。"""
    items = today_news(facts)
    if not items:
        return ""
    lines = [f"① {it['title']}" for it in items]
    return "这个世界今天发生了一些事：" + "；".join(lines) + "。"
