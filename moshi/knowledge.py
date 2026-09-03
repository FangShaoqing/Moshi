"""知识层（knowledge）· 本地部分 —— 她知道"今天是什么日子"。

- 日期/星期；二十四节气（寿星公式近似，±1 天可接受——"白露了"比精确到秒重要）；
- 时令描述（节气 → 季节语感：初秋转凉/深秋凝露/入冬…），供提示词/日子引用；
- 城市/天气：留接口（后续接天气 API 后再加，需要账号/密钥）。

原则：只提供"她世界的时间底色"，绝不编造具体事件（天气/新闻等级的在云阶段做）。
"""

from __future__ import annotations

import datetime

# 二十四节气（顺序：小寒→冬至；C 值为 21 世纪寿星公式系数）
TERMS_21C: list[tuple[str, float]] = [
    ("小寒", 5.4055), ("大寒", 20.12),
    ("立春", 3.87), ("雨水", 18.73),
    ("惊蛰", 5.63), ("春分", 20.646),
    ("清明", 4.81), ("谷雨", 20.1),
    ("立夏", 5.52), ("小满", 21.04),
    ("芒种", 5.678), ("夏至", 21.37),
    ("小暑", 7.108), ("大暑", 22.83),
    ("立秋", 7.5), ("处暑", 23.13),
    ("白露", 7.646), ("秋分", 23.042),
    ("寒露", 8.318), ("霜降", 23.438),
    ("立冬", 7.438), ("小雪", 22.36),
    ("大雪", 7.18), ("冬至", 21.94),
]
# 21 世纪若干特例（±1 天修正；太少可忽略——±1 天对语感无碍）
_EXCEPTIONS: dict[tuple[int, str], int] = {
    (2026, "小寒"): -1,
}

_TERM_MONTH = {
    "小寒": 1, "大寒": 1, "立春": 2, "雨水": 2, "惊蛰": 3, "春分": 3,
    "清明": 4, "谷雨": 4, "立夏": 5, "小满": 5, "芒种": 6, "夏至": 6,
    "小暑": 7, "大暑": 7, "立秋": 8, "处暑": 8, "白露": 9, "秋分": 9,
    "寒露": 10, "霜降": 10, "立冬": 11, "小雪": 11, "大雪": 12, "冬至": 12,
}


def _term_date(year: int, name: str, c: float) -> datetime.date:
    """寿星公式近似：D = int(Y*0.2422 + C) - int(Y/4)，Y=年份后两位。返回该节气日期。"""
    y = year % 100
    day = int(y * 0.2422 + c) - int(y / 4)
    day += _EXCEPTIONS.get((year, name), 0)
    return datetime.date(year, _TERM_MONTH[name], day)


def solar_terms(year: int) -> list[tuple[str, datetime.date]]:
    """一年的 24 个节气（名字, 日期）。"""
    return [(n, _term_date(year, n, c)) for n, c in TERMS_21C]


def today_info(d: datetime.date | None = None) -> dict:
    """今天：日期/星期/最近的节气/时令语感。"""
    d = d or datetime.date.today()
    week = "一二三四五六日"[d.weekday()]
    terms = solar_terms(d.year)
    prev, nxt = None, None
    for i, (n, dt) in enumerate(terms):
        if dt <= d:
            prev = (n, dt)
            nxt = terms[i + 1] if i + 1 < len(terms) else None
        else:
            nxt = (n, dt)
            break
    cur = prev[0] if prev else (terms[0][0] if terms else "")
    return {
        "date": d.isoformat(),
        "weekday": f"星期{week}",
        "solar_term": cur,
        "days_into_term": (d - prev[1]).days if prev else 0,
        "next_term": nxt[0] if nxt else "",
    }


def season_feel(term: str) -> str:
    """节气 → 她世界的时令语感（供提示词；不是天气预报，是"季节的底色"）。"""
    table = {
        "小寒": "一年里最冷的时候，天黑得早，人容易缩着",
        "大寒": "天寒地冻，快过年了",
        "立春": "风虽然还冷，但好像有点不一样了",
        "雨水": "时冷时暖，雨多",
        "惊蛰": "一声雷后，虫子都醒了",
        "春分": "白天和黑夜一样长",
        "清明": "天清地明，适合散步",
        "谷雨": "雨生百谷，春天快收尾",
        "立夏": "夏天来了，白天变长了",
        "小满": "麦子灌浆，小得盈满",
        "芒种": "该收该种，忙的时候",
        "夏至": "白昼最长，蝉叫得响",
        "小暑": "开始热了",
        "大暑": "一年最热",
        "立秋": "名义上的秋天，风还是热的",
        "处暑": "出暑，早晚开始凉",
        "白露": "露珠白了，早晚凉了，该添衣服了",
        "秋分": "昼夜平分，秋意刚好",
        "寒露": "露水更凉，秋天深了",
        "霜降": "开始见霜，冬天在门口",
        "立冬": "冬天开始了",
        "小雪": "飘小雪，天短了",
        "大雪": "雪下得大，天地白茫茫",
        "冬至": "黑夜最长，之后一天比一天亮",
    }
    return table.get(term, "")


def today_note(d: datetime.date | None = None) -> str:
    """一句话的知识底色（提示词引用）：'9月8日 星期三，白露——露珠白了，早晚凉了，该添衣服了'。"""
    info = today_info(d)
    feel = season_feel(info["solar_term"])
    m, day = info["date"][5:].split("-")
    prefix = f"{int(m)}月{int(day)}日 {info['weekday']}，{info['solar_term']}"
    return f"{prefix}——{feel}" if feel else prefix
