"""V4 相遇后的日子引擎（timeline）—— 她"遇到你之后"还在过日子（跨会话演化）。

设计（④；协作方确认 2026-08-31）：
- 她在生成时"一生已书写完毕"（过去完整）；**遇到你之后，她的日子继续往前走**：
  你不在这段时间里，她也在过自己的日子（妈妈打电话/加班/失眠/……）。
- **一个种子 = 一个宇宙 = 一份全部状态**（铁律）：全部日子状态都在
  `data/SHE_<seed>/world.json + life.json` 下；每天的发生由
  `random.Random(f"{seed}:life:{人生第N天}")` 确定性派生 —— **绝无全局状态、绝不跨种子共享**。
- **隐藏宇宙**（与你无关）：日子/配角是系统侧；对话里她按信任/时机提起最近的日子，系统不展示全貌。
- **确定性**：同种子 + 同时间线（同样的 last_day→today_day）→ 同样的日子（可复现）。
- ④ 本轮范围（阶段一+阶段二）：
  - **日常/情绪层**（她的日子、配角小事、心情基调、世界运势流动、日子→心情联动）；
  - **结构层**（毕业/搬家/换工作 → **事实层更新** + 配角增删）——结构性改变落在 facts 上
    （人生不许编：她的事实是真的变了，不是只改台词），发生一次记录一次（structure_log）。

机制（每天）：
1. 从 `Random(f"{seed}:life:{D}")` 派生今天发生的一件"日子"（她的 / 她世界里人的）；
2. `world.step()` —— 世界运势继续流动（她活在一个还在起伏的世界里）；
3. 每 3 天 `step_relations()` —— 配角状态/她对他们的依恋微动（天天动会失真）；
4. 近 7 天的日子基调 → `life_mood`（她最近过得怎么样）→ 被 Person.sync_from_life 消费（②联动）。
"""

from __future__ import annotations

import datetime
import random
from typing import Any

from ..v3.world import WorldState
from .facts import (JOB_POOL_MATURE, JOB_POOL_YOUNG, RESIDENCE_POOL_AFTER)
from .relations import MOOD_POOL, _things_for, step_relations, update_relations_for_context


def life_day_of(birth: datetime.date, today: datetime.date | None = None) -> int:
    """人生第几天（出生当天 = 0）。"""
    today = today or datetime.date.today()
    return (today - birth).days


# ── 心情判断词（与 Person.sync_from_life 的识别表一致）──
_DOWN_WORDS = ("闹", "别扭", "吵架", "烦", "担心", "生病", "累", "催",
               "失眠", "睡不着", "噎", "压", "提不起劲")
_UP_WORDS = ("好", "开心", "合得来", "暖和", "惦记", "踏实", "暖", "笑")


def _tone_of(text: str) -> int:
    """一句日子 → 情绪基调（-1 不好 / 0 平淡 / +1 不错）。"""
    if any(k in text for k in _DOWN_WORDS):
        return -1
    if any(k in text for k in _UP_WORDS):
        return 1
    return 0


# ── "她自己的日子"池（tag 与她的生活侧匹配：工作/在校/旧书店/通用）──
_HER_DAY: list[tuple[str, str, int]] = [
    # (tag, 日子, 基调)
    ("any",     "晚上翻来覆去睡不着，越想越清醒", -1),
    ("any",     "下雨了，她没带伞，在屋檐下站了十分钟", 0),
    ("any",     "路过花店，鬼使神差买了一束", 1),
    ("any",     "把手机里存的老照片翻出来看了一遍", 0),
    ("any",     "自己做了顿饭，虽然一般，但吃得很安静", 0),
    ("any",     "买了点水果，回去路上慢慢走", 0),
    ("any",     "今天状态还行，按部就班过了一天", 0),
    ("any",     "刷到一条老歌，听了一下午", 0),
    ("work",    "加班到挺晚，回到家已经十一点了", -1),
    ("work",    "开会时被点名，心提了一下", -1),
    ("work",    "做完了一件拖了很久的事，挺踏实的", 1),
    ("work",    "中午在便利店随便对付了一口", 0),
    ("study",   "上午的课她走神了，回过神来已经下课", 0),
    ("study",   "赶了一晚上作业，眼睛都花了", -1),
    ("shop",    "在旧书店淘到一本想找很久的书", 1),
    ("shop",    "去旧书店坐了一下午，没买什么", 0),
]


def _her_day_tags(facts: Any) -> list[str]:
    """她的生活侧 → 允许的 tag（跟事实走，不凭空造）。"""
    tags = ["any"]
    if facts is not None:
        job = getattr(facts, "job", "") or ""
        if job and "暂无" not in job:
            tags.append("work")
        edu = getattr(facts, "education_current", "") or ""
        if edu and "暂无" not in edu:
            tags.append("study")
        interests = " ".join(getattr(facts, "interests", ()) or ())
        if "旧书店" in interests:
            tags.append("shop")
    return tags


def _rel_event(relations: list[Any], rng: random.Random) -> tuple[str, int] | None:
    """她世界里的一件小事（配角在过日子）→ (文本, 基调)。"""
    rels = [r for r in relations if (_things_for(getattr(r, "kind", ""), getattr(r, "name", "")))]
    if not rels:
        return None
    rel = rng.choice(rels)
    pool = _things_for(rel.kind, rel.name)
    text = rng.choice(pool)
    rel.recent_thing = text                     # 配角的日子（她世界一致性）
    if rng.random() < 0.3:
        rel.mood = rng.choice(MOOD_POOL.get(rel.kind, ["还行"]))
    return (f"{rel.name}：{text}", _tone_of(text))


# ── "世界运势"接进她的日子（③：世界是活的——顺风让日子顺，逆风让日子沉）──
_WORLD_WIN: list[tuple[str, str, int]] = [
    ("any",  "今天运气不错，一件拖了很久的事突然有了着落", 1),
    ("work", "今天的事意外的顺利，她提前下了班", 1),
    ("shop", "旧书店老板说给她留了本好书，她抱回去看了很久", 1),
]
_WORLD_LOSS: list[tuple[str, str, int]] = [
    ("work", "忙到很晚，还有一堆没做完的，明天估计要挨说", -1),
    ("any",  "她算了算账，这个月又紧巴巴的，心里有点沉", -1),
    ("any",  "忽然有点慌：以后怎么办，她没想清楚", -1),
]
_WORLD_ACTION_DOMAINS = ("工作与生计", "金钱", "未来", "归属")


def _world_flavor(world: WorldState | None, rng: random.Random) -> tuple[str, int] | None:
    """世界运势 → 今天的日子带点"风"（顺风/逆风概率加权；逆风感更重——负面更影响人）。"""
    if world is None:
        return None
    try:
        res = getattr(world, "responses", {}) or {}
        if any(res.get(d, 0.0) < -0.25 for d in _WORLD_ACTION_DOMAINS) and rng.random() < 0.35:
            tag, text, tone = rng.choice(_WORLD_LOSS)
            return (text, tone)
        if any(res.get(d, 0.0) > 0.25 for d in _WORLD_ACTION_DOMAINS) and rng.random() < 0.20:
            tag, text, tone = rng.choice(_WORLD_WIN)
            return (text, tone)
    except Exception:
        pass
    return None


def _day_event(person: Any, relations: list[Any], rng: random.Random,
               ddate: datetime.date, birth: datetime.date,
               world: WorldState | None = None) -> tuple[str, int]:
    """今天发生的一件"日子"（她自己的 / 她世界里人的 / 世界运势的风）。"""
    # 生日（她在过日子——今天如果有生日，是她的日子的一部分；她自己不一定提）
    if (ddate.month, ddate.day) == (birth.month, birth.day):
        return ("今天是她的生日（她自己没特意提）", 1)
    # 世界运势的风（先于日常——世界会传染她的日子）
    flavor = _world_flavor(world, rng)
    if flavor is not None:
        return flavor
    # 40%：她世界里的人（她有自己的人际，日子里有他们）
    if relations and rng.random() < 0.4:
        got = _rel_event(relations, rng)
        if got:
            return got
    # 60%（或退路）：她自己的日子（跟她的生活侧匹配）
    tags = _her_day_tags(getattr(person, "facts", None))
    pool = [x for x in _HER_DAY if x[0] in tags] or [x for x in _HER_DAY if x[0] == "any"]
    tag, text, tone = rng.choice(pool)
    return (text, tone)


def _derive_mood(tones: list[int]) -> str:
    """近 7 天基调 → 她"最近的日子"（词表与 sync_from_life 的识别表一致）。"""
    if not tones:
        return "日子平平的，还算平静"
    avg = sum(tones) / len(tones)
    if avg <= -0.35:
        return "这两天心里有点烦，干什么都提不起劲"      # 烦 / 提不起劲 → 状态下调
    if avg <= -0.12:
        return "最近有点累，事情一桩接一桩"                # 累 → 状态下调
    if avg < 0.12:
        return "日子平平的，还算平静"                       # 平静 → 状态微升
    return "这几天过得挺踏实"                               # 踏实 → 状态微升


# ── ④ 阶段二 · 结构层：她的人生大事（毕业/搬家/换工作）──
# 铁律（人生不许编）：结构变化**真的改变事实**（facts 更新 + 持久化），配角随之增删
# （update_relations_for_context）——不是只改台词。确定性：`Random(f"{seed}:struct:{day}")` 派生。
STRUCT_DENSITY = 0.0025     # 随机结构事件密度（≈ 0.9 次/年；毕业是确定性锚点）


def graduation_date(birth: datetime.date) -> datetime.date:
    """毕业日（确定性锚点：入学≈18 岁，4 年制 → 出生+22 年 6 月底；与 facts 的入学口径一致）。"""
    return datetime.date(birth.year + 22, 6, 30)


def _structure_event(facts: Any, relations: list[Any], ddate: datetime.date,
                     day: int, seed: int, birth: datetime.date) -> dict | None:
    """今天是否发生结构性改变？→ 事件 dict 或 None。

    事件含 `facts`（变化后的事实值，作为"真相"持久化）+ `note`（她的日子日志文本）。
    ①②③ 按优先级：毕业（锚点）> 搬家/换工作（随机，密度低）。
    """
    rng = random.Random(f"{seed}:struct:{day}")
    if facts is None:
        return None
    edu = facts.education_current or ""

    # ① 毕业（确定性锚点：在读 → 本科毕业；搬出宿舍；第一份工作从应届池）
    if "在读" in edu and ddate >= graduation_date(birth):
        patch = {
            "education_current": f"本科毕业（{ddate.year}年毕业）",
            "residence": "合租的小单间",
            "job": rng.choice(JOB_POOL_YOUNG),
        }
        return {"day": day, "kind": "graduation", "tone": 0,
                "note": (f"{ddate.year}年6月底，她毕业了，搬出了学校宿舍；"
                         f"走之前和室友吃了顿饭，谁也没多说什么"),
                "facts": patch}

    # ② 随机结构事件（密度低；前提：不是应届未毕业的空转期）
    if rng.random() < STRUCT_DENSITY:
        # 搬家（任意阶段都真实存在；但宿舍→搬出通常是毕业，这里只管毕业后的搬家）
        if "在读" not in edu and facts.job and "暂无" not in facts.job:
            if rng.random() < 0.5:
                new_res = rng.choice(RESIDENCE_POOL_AFTER)
                if new_res != facts.residence:
                    return {"day": day, "kind": "move", "tone": -1,
                            "note": (f"她搬了家，现在住在{new_res}；"
                                     f"搬家那天，楼下的猫还在老地方，她回头看了一眼"),
                            "facts": {"residence": new_res}}
            # 换工作（工作在常理内流动）
            new_job = rng.choice(JOB_POOL_MATURE)
            if new_job != facts.job:
                return {"day": day, "kind": "job_change", "tone": 1,
                        "note": (f"她换了份工作（现在做{new_job}）；"
                                 f"走的那天，有同事说'以后常联系'"),
                        "facts": {"job": new_job}}
    return None


def _apply_structure(facts: Any, relations: list[Any], ev: dict, rng: random.Random) -> list[Any]:
    """应用一条结构事件：写事实（真相）+ 配角随生活情境增删。返回更新后的配角列表。"""
    if facts is not None:
        for k, v in (ev.get("facts") or {}).items():
            setattr(facts, k, v)
    new_rels = relations or []
    try:
        new_rels = update_relations_for_context(new_rels, facts, rng=rng)
    except Exception:
        pass
    # ④ 情感细节：搬家后，旧的"楼下猫"成了新楼下的猫（还没混熟）
    if ev.get("kind") == "move":
        for rel in new_rels:
            if getattr(rel, "kind", "") == "neighbor":
                rel.recent_thing = "新楼下也有一只猫，还没混熟"
                rel.mood = "半熟"
    return new_rels


def advance_days(person: Any, world: WorldState | None, relations: list[Any],
                 birth: datetime.date, last_day: int, today_day: int,
                 seed: int) -> dict:
    """推进 last_day+1 .. today_day 的日子（她照常过日子）。

    每天：
    - 结构层：先查"人生大事"（毕业/搬家/换工作）——有则今天是大事（日常让位），
      写事实（真相）+ 配角增删 + 记入 structure_log（持久化）；
    - `Random(f"{seed}:life:{D}")` 派生日常日子（确定性——同种子同时间线 → 同日子；绝不跨种子）；
    - world.step()（世界运势继续流动）；
    - 每 3 天 step_relations()（配角状态/依恋微动——天天动会失真）；
    - 近 7 天基调 → person.life_mood（② 联动：sync_from_life 消费 → 今天心情受影响）。

    返回 {"advanced": n, "structure": [事件...], "relations": 当前配角列表}
    （n = 推进天数；structure = 本轮发生的大事；relations = 更新后的配角——若被替换请用回）。
    """
    entries: list[dict] = list(getattr(person, "life_log", []) or [])
    structure_fired: list[dict] = []
    advanced = 0
    for day in range(last_day + 1, today_day + 1):
        rng = random.Random(f"{seed}:life:{day}")
        ddate = birth + datetime.timedelta(days=day)
        # 结构层：人生大事优先（日常让位）
        facts = getattr(person, "facts", None)
        ev = _structure_event(facts, relations, ddate, day, seed, birth)
        if ev is not None:
            relations = _apply_structure(facts, relations, ev,
                                         random.Random(f"{seed}:struct:{day}"))
            if getattr(person, "structure_log", None) is None:
                person.structure_log = []
            person.structure_log.append(ev)
            structure_fired.append(ev)
            text, tone = ev["note"], ev.get("tone", 0)
        else:
            text, tone = _day_event(person, relations, rng, ddate, birth, world=world)
        entries.append({"day": day, "date": ddate.isoformat(), "text": text, "tone": tone})
        advanced += 1
        # 世界继续流动（她活在一个还在起伏的世界里）
        if world is not None:
            try:
                world.step(rng)
            except Exception:
                pass
        # 配角的日子/依恋微动（每 3 天一次——天天动会失真）
        if relations and day % 3 == 0:
            try:
                step_relations(relations, rng)
            except Exception:
                pass
    # 写入人格：近 7 条日志 + 最近基调（她"最近过得怎么样"）
    person.life_log = entries[-7:]
    tones = [e["tone"] for e in person.life_log]
    person.life_mood = _derive_mood(tones)
    person.life_recent = "；".join(e["text"] for e in person.life_log[-3:])
    person.life_advanced_total = int(getattr(person, "life_advanced_total", 0) or 0) + advanced
    return {"advanced": advanced, "structure": structure_fired, "relations": relations}
