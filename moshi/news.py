"""天行数据（news）—— 她"偶尔知道世界发生了一点点事"（不是播报机器）。

原则（设计定稿）：
- 数据：天行数据免费新闻接口（key=config/secrets.json NEWS_API_KEY；环境变量 NEWS_API_KEY 兜底）；
- **克制**：每日缓存（6h），只取她可能留意的分类（默认综合头条，可配），**只留 2 条**；
- **不播报**：给 LLM 的字样是"这个世界今天发生了一些事——她可能知道也可能不在意"；
  她提到也是"跟自己有关"或一句自己的看法，不是背新闻稿；
- **人生不许编**：新闻事实来自接口，她只说给定条目/自己的感受，不即兴编细节；
- 无 key/网络失败 → 空（优雅降级）。
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
CATEGORIES = ("generalnews",)      # 综合新闻头条（可加 "yule" 等；她的关注面保持克制）
KEEP = 2                            # 只留 2 条（她不会关心一堆新闻）
TTL = 6 * 3600                      # 每日几次缓存


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


def _fetch(cat: str) -> list[dict]:
    key = news_key()
    if not key:
        return []
    url = f"{API}/{cat}/index?key={key}&num=10"
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


def today_news() -> list[dict]:
    """她可能留意的新闻（缓存 6h；条目：{title, source}）。无 key → []。"""
    cache = _load_cache()
    hit = cache.get("news", {})
    if hit.get("t") and time.time() - hit["t"] < TTL:
        return hit.get("items", [])
    items: list[dict] = []
    for cat in CATEGORIES:
        for n in _fetch(cat):
            title = (n.get("title") or "").strip()
            if title and not any(dup.get("title") == title for dup in items):
                items.append({"title": title, "source": (n.get("source") or "").strip()})
            if len(items) >= KEEP:
                break
        if len(items) >= KEEP:
            break
    _save_cache(_load_cache() | {"news": {"t": time.time(), "items": items[:KEEP]}})
    return items[:KEEP]


def news_note() -> str:
    """一句话给 LLM（克制版）：'这个世界今天有一些事：①…；②…'——她可能知道也可能不在意。"""
    items = today_news()
    if not items:
        return ""
    lines = [f"① {it['title']}" for it in items]
    return "这个世界今天发生了一些事：" + "；".join(lines) + "。"
