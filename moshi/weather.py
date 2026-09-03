"""天气（weather）—— 和风天气（QWeather）：她"知道今天外面是什么天气"。

- Key：config/secrets.json 的 `QWEATHER_KEY`（环境变量 QWEATHER_KEY 兜底）；
  和风免费版（devapi.qweather.com）个人自用额度充足；
- 城市：由她的 facts.current_city（杭州/成都…）→ GeoAPI 定位（缓存 7 天）；
- 数据：实时天气（温度/天况/体感/风）+ 生活指数（穿衣/雨伞）——30 分钟缓存；
- 无 key/网络失败 → 返回空串（句子优雅降级，只有节气），绝不抛出。

原则：只提供"今天外面"的事实，不编造。
"""

from __future__ import annotations

import datetime
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_KEY_FILE = _ROOT / "config" / "secrets.json"
_CACHE_FILE = _ROOT / "data" / "weather_cache.json"

_URL = "https://devapi.qweather.com"


def qweather_key() -> str:
    env = os.environ.get("QWEATHER_KEY", "").strip()
    if env:
        return env
    try:
        if _KEY_FILE.exists():
            v = (json.loads(_KEY_FILE.read_text(encoding="utf-8")).get("QWEATHER_KEY") or "").strip()
            if v and not v.startswith("在此"):
                return v
    except Exception:
        pass
    return ""


def _get(url: str, timeout: int = 15) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "moshi/selfuse"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
            if d.get("code") == "200":
                return d
    except Exception:
        pass
    return None


def _cache() -> dict:
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


def _city_id(city: str) -> str | None:
    """GeoAPI 城市定位（缓存 7 天）。返回 LocationID。"""
    c = _cache().get("geo", {})
    hit = c.get(city, {})
    if hit.get("id") and time.time() - hit.get("t", 0) < 7 * 24 * 3600:
        return hit["id"]
    key = qweather_key()
    if not key:
        return None
    d = _get(f"{_URL}/geo/v2/city/lookup?location={urllib.parse.quote(city)}&key={key}")
    if not d:
        return None
    loc = (d.get("location") or [{}])[0]
    cid = loc.get("id")
    if cid:
        c[city] = {"id": cid, "t": time.time()}
        _save_cache(_cache() | {"geo": c})
    return cid


def now_weather(city: str) -> dict | None:
    """实时天气句（她的城市）：{'text','temp','feels','wind','dressing','umbrella'} 或 None。"""
    key = qweather_key()
    if not key:
        return None
    cid = _city_id(city)
    if not cid:
        return None
    cache = _cache().get("w", {})
    hit = cache.get(cid, {})
    if hit.get("t") and time.time() - hit["t"] < 30 * 60:
        return hit["data"]
    d = _get(f"{_URL}/v7/weather/now?location={cid}&key={key}")
    if not d:
        return None
    now = (d.get("now") or {})
    data = {
        "text": now.get("text", ""),
        "temp": now.get("temp", ""),
        "feels": now.get("feelsLike", ""),
        "wind": now.get("windDir", "") + (now.get("windScale", "") and f"{now['windScale']}级" or ""),
        "dressing": "",
        "umbrella": "",
    }
    # 生活指数（穿衣/雨伞；1 天预报）
    ind = _get(f"{_URL}/v7/indices/1d?type=3,9&location={cid}&key={key}")
    if ind:
        for item in (ind.get("daily") or []):
            if item.get("type") == "3":
                data["dressing"] = (item.get("text", "").split("，") or [""])[0]
            elif item.get("type") == "9":
                data["umbrella"] = (item.get("text", "").split("，") or [""])[0]
    cache[cid] = {"t": time.time(), "data": data}
    _save_cache(_cache() | {"w": cache})
    return data


def weather_note(city: str = "") -> str:
    """一句话天气（提示词引用）：'多云，21°C，体感 19°C——早晚凉，出门带伞'。无 key 返回空。"""
    if not city:
        return ""
    w = now_weather(city)
    if not w:
        return ""
    parts = [w["text"], f"{w['temp']}°C"]
    if w.get("feels"):
        parts.append(f"体感{w['feels']}°C")
    note = "，".join(p for p in parts if p)
    tips = []
    if w.get("dressing"):
        tips.append(w["dressing"])
    if w.get("umbrella"):
        tips.append(w["umbrella"])
    if tips:
        note += "——" + "，".join(tips)
    return note
