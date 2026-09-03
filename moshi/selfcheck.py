"""自检套件（selfcheck）—— 一键回归：她（各机制）是否还健全。

用法：python -m moshi.selfcheck            # 全部离线检查（生成/模型不跑）
说明：网络/模型类（天气实调、新闻实调、DeepSeek、生图）不在此列——它们由真机验证负责。
"""

from __future__ import annotations

import datetime
import random

TOTAL = 0
PASSED = 0
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global TOTAL, PASSED
    TOTAL += 1
    if cond:
        PASSED += 1
        print(f"  ✅ {name}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}  {detail}")


def run() -> None:
    print("== 自检：她（离线机制）==")

    # ── 事实层（人生不许编的地基）──
    from .v3.generate import generate_person
    from .v4.facts import facts_to_dict, facts_from_dict
    from .v4.person import Person

    res = generate_person(424242)
    f = res["facts"]
    check("事实：形象四元组非空", bool(f.height and f.hair and f.face and f.style))
    check("事实：序列化 roundtrip", facts_to_dict(facts_from_dict(facts_to_dict(f))) == facts_to_dict(f))

    # ── 人格/依恋/关系 ──
    p = Person(seed=424242, birth_date=res["birth_date"], age=res["current_age"], facts=f)
    p.build_flaws()
    check("人格：有缺点", len(p.flaws) >= 2)
    check("人格：依恋类型可推导", p.attachment_style() in ("安全型", "焦虑型", "回避型", "矛盾型", "独立型", "观望型"))
    check("人格：初始关系=初识", p.relationship_stage() == "初识")

    # ── 相遇背景（她记得你们怎么认识的）──
    from .v4.meeting import generate_meeting_story, story_context
    story = generate_meeting_story(424242, f)
    check("相遇：叙事完整", all(k in story for k in ("scene", "place", "duration", "spark", "narrative")))
    check("相遇：确定性", story == generate_meeting_story(424242, f))
    p.meeting_story = story
    check("相遇：起点=熟悉", p.relationship_stage() == "熟悉")

    # ── 知识层（节气/节日）──
    from . import knowledge
    terms = dict(knowledge.solar_terms(2026))
    check("知识：24 节气", len(terms) == 24)
    check("知识：白露≈9/7-8", abs((terms["白露"] - datetime.date(2026, 9, 7)).days) <= 1)
    check("知识：中秋 2026-09-25", knowledge.festival_of(datetime.date(2026, 9, 25)) == "中秋")
    check("知识：非节日常", knowledge.festival_of(datetime.date(2026, 3, 11)) == "")
    check("知识：今日一句话非空", bool(knowledge.today_note()))

    # ── 天气（无 key 优雅降级；解析）──
    from . import weather
    check("天气：key 读取或占位（无 key 时为空串）", isinstance(weather.qweather_key(), str))
    check("天气：weather_note 不抛错", isinstance(weather.weather_note("成都"), str))

    # ── 新闻（兴趣驱动：她是谁→她关心什么）──
    from . import news
    from .v4.facts import Facts as _F
    def _mk(major="", job="", interests=()):
        _f = _F(); _f.major, _f.job, _f.interests = major, job, tuple(interests); return _f
    check("新闻：软件工程→tech", news.her_domains(_mk(major="软件工程"))[0] == "tech")
    check("新闻：护士→medical", "medical" in news.her_domains(_mk(job="护士")))
    check("新闻：无 key 时 news_note 为 str", isinstance(news.news_note(), str))
    check("新闻：无关题 0 分", news._score("足球联赛决赛", ("tech", "society")) == 0)

    # ── 照片（决策层，不生成）──
    from . import photo
    ph = Person(seed=424242, birth_date=res["birth_date"], age=res["current_age"], facts=f)
    ph.interaction_count = 60
    ph.is_angry = True
    check("照片：生气不发", photo.decide_photo(ph) is None)
    ph.is_angry = False
    check("照片：日子说场景", "night_street" in photo.scene_keys_from_life(
        type("X", (), {"life_log": [{"text": "加班到挺晚，回到家已经十一点了", "day": 1}], "life_mood": ""})))

    # ── 声音（决策层：她选文字/语音）──
    from . import voice
    vs = Person(seed=424242, birth_date=res["birth_date"], age=res["current_age"], facts=f)
    check("声音：长话→文字", not voice.decide_voice(vs, "chat", "长" * 61))
    vs.is_angry = True
    check("声音：生气→文字", not voice.decide_voice(vs, "chat", "嗯"))
    vs.is_angry = False
    check("声音：空回复→文字", not voice.decide_voice(vs, "chat", ""))

    # ── 日子引擎（确定性）──
    from .v4 import timeline
    from .v4.relations import build_relations
    def _advance_twice():
        from .v3.generate import generate_person as _g
        out = []
        for _ in range(2):
            r = _g(555)
            pp = Person(seed=555, birth_date=r["birth_date"], age=r["current_age"],
                        facts=r["facts"], state=r["steps"][-1].state)
            rels = build_relations(r["facts"], [], rng=random.Random(f"{555}:rel"))
            today = timeline.life_day_of(r["birth_date"])
            timeline.advance_days(pp, r["world"], rels, r["birth_date"], today - 3, today, 555)
            out.append((pp.life_log, pp.life_mood))
        return out
    try:
        a, b = _advance_twice()
        check("日子：同种子同时间线→同日子", a == b)
    except Exception as e:
        check("日子：同种子同时间线→同日子", False, str(e)[:60])

    print(f"\n== 结果：{PASSED}/{TOTAL} 通过 ==")
    if FAILED:
        print("失败项：", "；".join(FAILED))


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    run()
    sys.exit(0 if FAILED == [] else 1)
