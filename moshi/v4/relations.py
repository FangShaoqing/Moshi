"""V4 关系网（relations）—— 她世界里的人（自适应生成 + 隐藏宇宙）。

设计（协作方确认）：
- **自适应生成**：配角由她的"生活情境"（生活阶段/环境）动态确定——
  - 在校 → 室友/同学；已工作 → 同事；搬家过 → 新邻居；有兴趣 → 常去地方的店主；
  - 生活情境变化（毕业/换工作/搬家）→ 配角**自动增删**（室友淡出、新同事出现）；
  - **非"每天实时变化"**（那属在线阶段），随人生阶段/环境变。
- **完全隐藏（隐藏宇宙）**：配角是**系统侧**——用户**看不到**"她世界里的人"；
  只能在**对话中**（她按信任/时机提起）得知；**你拼出她的世界，而非审阅**。
- **轻量**：配角有"身份 + 碎片 + 状态"（有日子），非完整人生。

原则：配角需要"与她的生活一致"（挂在她的事实/情境上，非凭空）；她提及时有厚度（具体/带温度）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass
class Relation:
    """她世界里的一个人（轻量存在）。"""
    name: str                 # 称呼（我妈 / 室友 / 楼下橘猫 / 新同事）
    kind: str                 # family / roommate / classmate / neighbor / shopkeep / workmate
    base_fact: str            # 身份事实（挂在她的事实/情境上）
    mood: str
    recent_thing: str
    bonds_with_her: str
    # ── 配角×依恋联动：她对他/她的"依恋"（人对不同关系有不同依恋；真实的人如此）──
    # proximity（亲近度 0~1）：她对这人的距离感；tendency：往"靠"还是"避"。
    proximity: float = 0.5
    tendency: str = "plain"   # towards（亲近/靠近） / avoid（想躲/有心结） / plain（普通）

    def describe_recent(self) -> str:
        return f"{self.base_fact}；最近{self.recent_thing}（{self.mood}）"

    def attachment_note(self) -> str:
        """她对这人的依恋底色（供 LLM：提起时语气/温度依此不同）。"""
        if self.tendency == "towards":
            return f"她对他有点亲近（会惦记、会愿意说）"
        if self.tendency == "avoid":
            return f"她和他有心结/有点想躲（提起时会收着或不自然）"
        return "她和他关系平常（不特别近也不疏远）"

    # ── 配角依恋随演化：关系随日子微动（真实：关系有起伏、会反复，不会单调冲向一端）──
    def evolve_attachment(self, rng: random.Random) -> None:
        """一次日子后，她对这人的亲近/倾向轻微漂移（有起伏、会反复——真实关系）。

        规则（轻量——真实人生里关系是"起起落落"的，不是单调变好/变坏）：
        - proximity 每次小幅漂移，**有正有负**（关系会起伏：好的时候近、别扭的时候远）；
        - "倾向引力"只是**微弱的偏向**（towards 略偏近、avoid 略偏远），**不是单向锁定**；
        - 偶尔一次"事"（变故/契机）导致较明显的反向跳（不是天天，是偶尔）；
        - tendency 偶尔切换（心结可能化开；亲近可能淡；平常可能走近）——慢慢变，非突跳。
        """
        # 日常漂移：有正有负（平均值 0；只是倾向引力极轻微偏置，避免单调锁死）
        drift = rng.uniform(-0.10, 0.10)
        if self.tendency == "towards":
            drift += 0.015
        elif self.tendency == "avoid":
            drift -= 0.015
        self.proximity = max(0.0, min(1.0, self.proximity + drift))
        # 偶尔一次"事"：较明显的反向跳（不是天天——是机缘，让关系有起伏）
        if rng.random() < 0.08:
            # 事让关系近一点或远一点（方向随机）
            jump = rng.choice([-0.18, 0.18])
            self.proximity = max(0.0, min(1.0, self.proximity + jump))
        # tendency 缓慢切换（真实：心结会慢慢化开/亲近会淡，但非突跳）
        if self.tendency == "avoid" and self.proximity > 0.6 and rng.random() < 0.15:
            self.tendency = "plain"
            self.bonds_with_her = "在慢慢缓和"
        elif self.tendency == "towards" and self.proximity < 0.35 and rng.random() < 0.1:
            self.tendency = "plain"
        elif self.tendency == "plain" and rng.random() < 0.08:
            if self.proximity > 0.55:
                self.tendency = "towards"


# ── 碎片池（具体/带温度；配角"此刻在过什么日子"）──
DAY_THINGS: dict[str, list[str]] = {
    "family": [
        "又打电话催她找对象，她有点烦", "问她过得怎么样，说想她了",
        "在老家说身体有点小毛病，她挺担心", "念叨让她少熬夜，她嘴上应着没听进去",
        "说家里今年收成一般，让她别担心", "问她钱够不够花，她说不缺",
    ],
    "roommate": [
        "晚上回来很晚，好像又在加班", "总跟她一起吃饭，挺合得来",
        "在谈一个对象，心情不错", "最近减肥，晚上饿得睡不着",
        "把她那边的灯开着，她有点睡不着", "今天回老家了，宿舍就她一个人",
    ],
    "classmate": [
        "好久没联系了，偶尔想起", "毕业之后去了别的城市",
        "还留在学校读研，偶尔问候", "结婚那天给她发过请柬，她没去",
    ],
    "neighbor": [
        "楼下那只橘猫老蹭她的腿", "隔壁宿舍的同学总来借东西",
        "楼下阿姨见她总问'吃饭没'", "楼道里常碰见的一个女生，会点点头",
    ],
    "shopkeep": [
        "旧书店老板总给她留书", "她常去的那家店老板记得她爱看的类型",
        "老板把新到的书给她留着", "店里养了只猫，她去就摸两把",
    ],
    "workmate": [
        "总在群里发消息，有点烦", "最近项目忙，经常加班到很晚",
        "她们组的一个前辈，挺照顾她", "上周请假了，工作堆了一堆",
    ],
}

MOOD_POOL: dict[str, list[str]] = {
    "family": ["总惦记她", "身体不太利索但嘴硬", "安稳过日子", "嘴上唠叨心里疼她"],
    "roommate": ["挺安静的", "跟她合得来", "最近累", "心情不错"],
    "classmate": ["淡了，但还有点交情", "偶尔想起", "已经各忙各的"],
    "neighbor": ["半熟", "点头之交", "看着挺温和"],
    "shopkeep": ["熟客", "记得她", "话不多但人好"],
    "workmate": ["普通同事", "稍微有点距离", "还算客气"],
}

# ── 邻居碎片分池：猫的事归猫、半熟人的事归人（质感：别让猫说人的事）──
_CAT_THINGS = ["夜里在楼下叫了两声，她听见了", "老蹭她的腿，她蹲下摸了摸",
               "她把猫粮放在门口，它吃完了", "今天没见着，她有点惦记"]
_PEOPLE_THINGS = ["楼道里常碰见的一个女生，会点点头", "隔壁的同学总来借东西",
                  "楼下阿姨见她总问'吃饭没'"]


def _things_for(kind: str, name: str = "") -> list[str]:
    """按"角色"取碎片池（楼下橘猫说猫的事；邻居半熟人说人的事）。"""
    if kind == "neighbor":
        return _CAT_THINGS if "猫" in (name or "") else _PEOPLE_THINGS
    return DAY_THINGS.get(kind, [])


# ── 生活情境：由她的事实推导（决定有哪些配角）──
def _life_context(facts: Any) -> dict:
    """她的生活情境：身份/求学/工作/住所/兴趣（配角由此自适应）。"""
    return {
        "residence": getattr(facts, "residence", ""),
        "job": getattr(facts, "job", ""),
        "education": getattr(facts, "education_current", ""),
        "interests": list(getattr(facts, "interests", ()) or ()),
    }


def relation_templates_for(facts: Any, memories_text: str,
                           rng: random.Random) -> list[dict]:
    """由生活情境/记忆，推导"此刻她世界里该有谁"（模板；未实例化）。"""
    ctx = _life_context(facts)
    templates: list[dict] = []

    # 家庭（一直有，非情境变化——但随事实定）
    if facts is not None:
        mom_job = facts.parents_job[0] if facts.parents_job and facts.parents_job[0] else "退休在家"
        dad_job = facts.parents_job[1] if len(facts.parents_job) > 1 and facts.parents_job[1] else ""
        structure = ("她父母离异了，跟着妈妈过" if facts.family_structure == "离异"
                     else "她爸妈的婚姻还算平稳")
        # 依恋派生：离异（跟妈妈）→ 和妈的亲近/心结；她性格信任弱 → 对家人也收着
        mom_att = ("avoid" if facts.family_structure == "离异" else "towards")
        templates.append({
            "name": "我妈", "kind": "family",
            "base_fact": f"{structure}；她妈在老家，原来是{mom_job}"
                         + (f"（她爸是{dad_job}）" if dad_job else ""),
            "bonds": "亲近但有点心结" if facts.family_structure == "离异" else "亲近",
            "att_prox": 0.45 if mom_att == "avoid" else 0.7,
            "att_tend": mom_att,
        })
        if facts.siblings >= 1:
            templates.append({"name": "我弟/妹" if facts.siblings == 1 else "我哥/姐",
                              "kind": "family",
                              "base_fact": "她家里还有个手足",
                              "bonds": "还行",
                              "att_prox": 0.6, "att_tend": "towards"})

    # 在校 → 室友/同学（宿舍）；已工作 → 同事；搬家后 → 新邻居
    if "宿舍" in ctx["residence"]:
        templates.append({"name": "室友", "kind": "roommate",
                          "base_fact": f"她{ctx['residence']}，和室友合住", "bonds": "合得来",
                          "att_prox": 0.65, "att_tend": "towards"})
        if any(k in memories_text for k in ("朋友", "同学", "同桌")):
            templates.append({"name": "学生时代的朋友", "kind": "classmate",
                              "base_fact": "她学生时代的一个朋友", "bonds": "淡了",
                              "att_prox": 0.4, "att_tend": "plain"})
    elif ctx["job"] and "暂无" not in ctx["job"]:
        templates.append({"name": "同事", "kind": "workmate",
                          "base_fact": "她工作地方的同事", "bonds": "普通",
                          "att_prox": 0.45, "att_tend": "plain"})

    # 兴趣 → 常去地方的店主（生活层，随生活情境）
    if any("旧书店" in x for x in ctx["interests"]):
        templates.append({"name": "旧书店老板", "kind": "shopkeep",
                          "base_fact": "她常去的那家旧书店的老板，认得她爱看的书",
                          "bonds": "熟客交情",
                          "att_prox": 0.5, "att_tend": "plain"})
    # 住所 → 楼下/邻居（生活层）
    if ctx["residence"]:
        templates.append({"name": "楼下橘猫", "kind": "neighbor",
                          "base_fact": "她住的地方楼下有一只常来蹭的橘猫",
                          "bonds": "半熟：她偶尔喂喂它",
                          "att_prox": 0.55, "att_tend": "towards"})

    return templates


def build_relations(facts: Any, memories: list[Any] | None = None,
                    rng: random.Random | None = None) -> list[Relation]:
    """从她的生活情境派生配角（自适应——情境变则配角变）。

    注意（隐藏宇宙）：这是**系统侧**；用户**看不到**"她世界里的人"，
    只能在对话中（她按信任/时机提起）得知。
    """
    rng = rng or random
    mem_text = " ".join(m.text for m in (memories or []))
    templates = relation_templates_for(facts, mem_text, rng)
    relations: list[Relation] = []
    for tpl in templates:
        _pool = _things_for(tpl["kind"], tpl["name"]) or ["最近没什么特别的事"]
        relations.append(Relation(
            name=tpl["name"], kind=tpl["kind"], base_fact=tpl["base_fact"],
            mood=rng.choice(MOOD_POOL.get(tpl["kind"], ["还行"])),
            recent_thing=rng.choice(_pool),
            bonds_with_her=tpl["bonds"],
            proximity=tpl.get("att_prox", 0.5),
            tendency=tpl.get("att_tend", "plain"),
        ))
    return relations


def update_relations_for_context(relations: list[Relation], new_facts: Any,
                                 memories_text: str = "",
                                 rng: random.Random | None = None) -> list[Relation]:
    """生活情境变化 → 配角自动增删（毕业→室友淡出；工作→同事出现；搬家→新邻居）。

    规则：情境里"该有"的配角保留/新增；"不该有"的移出（或标"淡出"）。
    """
    rng = rng or random
    templates = relation_templates_for(new_facts, memories_text, rng)
    wanted_kinds = {t["kind"] for t in templates}
    updated: list[Relation] = []
    for rel in relations:
        if rel.kind in wanted_kinds:
            updated.append(rel)
    # 新增情境里"该有但还没有"的
    existing_kinds = {r.kind for r in updated}
    for tpl in templates:
        if tpl["kind"] not in existing_kinds:
            _pool = _things_for(tpl["kind"], tpl["name"]) or ["最近没什么特别的事"]
            updated.append(Relation(
                name=tpl["name"], kind=tpl["kind"], base_fact=tpl["base_fact"],
                mood=rng.choice(MOOD_POOL.get(tpl["kind"], ["还行"])),
                recent_thing=rng.choice(_pool),
                bonds_with_her=tpl["bonds"],
                proximity=tpl.get("att_prox", 0.5),
                tendency=tpl.get("att_tend", "plain")))
    return updated


def step_relations(relations: list[Relation], rng: random.Random | None = None) -> None:
    """她世界的"日子"演化一步：配角的状态/小事/依恋都随日子微动（真实人生关系是流动的）。

    - mood / recent_thing：配角"此刻在过什么日子"轻微漂移；
    - evolve_attachment：她对各配角的依恋（proximity/tendency）随日子慢慢变
      （心结可能化开、亲近可能淡、平常可能走近——像真实关系）。
    """
    rng = rng or random
    for rel in relations:
        if rel.kind in DAY_THINGS or rel.kind == "neighbor":
            if rng.random() < 0.35:
                rel.mood = rng.choice(MOOD_POOL.get(rel.kind, ["还行"]))
            if rng.random() < 0.3:
                rel.recent_thing = rng.choice(
                    _things_for(rel.kind, rel.name) or ["最近没什么特别的事"])
        # 依恋随演化（每天都有机会微动——关系不会停在某一态）
        rel.evolve_attachment(rng)
