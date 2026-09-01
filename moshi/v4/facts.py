"""V4 事实库（facts）—— 她是谁的"硬事实"（系统定义，LLM 只能引用、不许编造）。

动机：现有 V3 只生成"记忆碎片（大事年 + 认识）"，缺**结构化身份事实**（家庭/求学/工作/城市），
导致 LLM 被问"你有几个兄弟姐妹/你在哪工作"时**无事实可用 → 只能编造**（"就我一个""城南设计公司"）。
本模块由种子在"合法候选池"内生发这些事实（非造物主设定），并与 V3 的演化共用同一视角。

一致性原则：
- 家庭阶层（贫困/普通/小康/富足）→ 映射父母职业结构（贫困=体力/零工；富足=经商/技术岗等）；
- 家庭氛围（温暖/冷淡/紧张/动荡）→ 影响家庭结构（动荡/紧张 = 可能父母离异/单亲）；
- 求学路径由出生年份 + 年龄决定（2000-2006 出生，2020s 成年：20-26 岁 = 在读大学/刚毕业/工作几年）。
- 城市：从 V4 世界运势的"顺/逆风"不直接可得，这里用独立候选池（省/城市）由种子选。

诚实说明：V3 的记忆叙事（"家里为钱吵过架"）与 facts 的"贫困"之间目前**不强校验**——真实系统
最好在生成时让两者同源（同一候选池派生）。V4 先用"同种子派生 + 语义合理"，够用于最小验证。
"""

from __future__ import annotations

import datetime
import random
from dataclasses import dataclass, field
from typing import Any


# ── 合法候选池（真实可行）──

# 家庭阶层 → 父母职业结构候选（与 V3 先在条件的"家庭阶层"语义对齐）
FAMILY_CLASS_TO_PARENTS: dict[str, list[tuple[str, str]]] = {
    "贫困": [("工厂工人", "裁缝"), ("零工", "清洁工"), ("务农", "务农")],
    "普通": [("工厂职工", "小学教师"), ("个体户", "售货员"), ("公司职员", "会计")],
    "小康": [("中学教师", "国企职工"), ("医生", "护士"), ("工程师", "公务员")],
    "富足": [("经商", "全职太太"), ("企业高管", "设计师"), ("私营业主", "医生")],
}

# 家庭氛围 → 家庭结构权重（动荡/紧张 → 真实家庭不完整可能性高）
FAMILY_ATMOSPHERE_STRUCTURE: dict[str, list[str]] = {
    "温暖": ["双亲", "双亲", "双亲"],
    "冷淡": ["双亲", "双亲", "双亲"],
    "紧张": ["双亲", "离异", "双亲"],
    "动荡": ["离异", "双亲", "离异"],
}

# 省份/城市候选（真实）
CITIES: list[tuple[str, str]] = [
    ("浙江", "杭州"), ("四川", "成都"), ("湖北", "武汉"),
    ("江苏", "南京"), ("福建", "福州"), ("安徽", "合肥"),
    ("河南", "郑州"), ("湖南", "长沙"), ("广东", "广州"),
]

# 学校类型 + 专业候选（与年龄一致：在读/刚毕业）
SCHOOL_TYPES: list[str] = ["普通本科", "一本院校", "职业技术学院"]
MAJORS: list[str] = ["视觉传达", "汉语言文学", "新闻传播", "会计学", "软件工程",
                     "学前教育", "市场营销", "护理学"]

# 兴趣爱好（2-3 个，克制、贴近她的性格：沉静内敛）
INTEREST_POOL: list[str] = ["看路边花", "听歌", "散步", "看小说", "做饭",
                            "画画", "写点东西", "逛旧书店", "跑步", "做手账"]

# 生活习性（一句）
KEEPS_POOL: list[str] = [
    "习惯一个人吃饭，喜欢安静",
    "周末会睡懒觉，然后发呆",
    "不太主动联系别人",
    "睡前会看一会儿书",
]

# 住所
RESIDENCE_POOL: list[str] = ["学校宿舍", "合租的小单间", "家里人给租的房子", "城中村的一间"]

# ── 结构层（④ 阶段二）：毕业后/工作中的事实候选（与 generate_facts 同池，保证同源）──
JOB_POOL_YOUNG: list[str] = ["设计助理", "编辑", "店员", "行政专员"]        # 应届/毕业不久
JOB_POOL_MATURE: list[str] = ["平面设计", "文案策划", "新媒体运营", "会计助理"]  # 工作几年
RESIDENCE_POOL_AFTER: list[str] = ["合租的小单间", "城中村的一间", "自己租的一居室", "和家人住"]


@dataclass
class Facts:
    """她的硬事实（系统侧定义）。LLM 只能引用这些，不得编造。

    设计（乙-完整事实库）：覆盖"她的一切可断言事实"：
    - 身份：出生地/现居城市/性格关键词
    - 家庭：阶层/父母职业/兄弟姐妹/家庭结构
    - 求学：学校类型/就读状态/专业方向
    - 工作：职业/工作状态
    - 生活：住所/兴趣爱好/生活习性
    - 情感：感情状态（基于年龄与记忆演化的合理推断）
    注：这是**系统侧**（校验/约束用），她不会自己盘点；她只凭记忆+性格说话。
    """
    # 身份
    birth_place_city: str = ""
    birth_place_province: str = ""
    current_city: str = ""
    # 家庭
    family_class: str = "普通"
    parents_job: tuple[str, str] = ("", "")
    siblings: int = 0
    family_structure: str = "双亲"
    # 求学
    school_type: str = ""                # 大学类型（本科/职业技术学院）
    education_current: str = ""          # 当前状态（在读大学/已毕业）
    major: str = ""                      # 专业/方向
    # 工作
    job: str = ""
    working_city: str = ""
    # 生活
    residence: str = ""                  # 住所（宿舍/租房等）
    interests: tuple[str, ...] = ()      # 兴趣爱好（2-3 个）
    keeps: str = ""                      # 生活习性（简单一句）
    # 情感
    relationship_status: str = "单身"     # 单身/有过一段/恋爱中（由年龄+演化合理推断）

    def describe(self) -> str:
        return self.to_context()

    def to_context(self) -> str:
        """给 LLM 的"她的事实"完整清单（**唯一真实来源**，只许引用，不得编造）。"""
        fam = f"{self.family_structure}，{'独生' if self.siblings == 0 else f'{self.siblings}个兄弟姐妹'}"
        parts = [
            f"身份：女，出生在{self.birth_place_province}{self.birth_place_city}，现在在{self.current_city}",
            f"家庭：{self.family_class}（父母：{self.parents_job[0]}、{self.parents_job[1]}；{fam}）",
            f"求学：{self.education_current}{'，' + self.school_type if self.school_type else ''}，专业{self.major if self.major else '（未定）'}",
            f"工作：{self.job}",
            f"生活：{self.residence}；喜欢{'、'.join(self.interests) if self.interests else '（未定）'}；{self.keeps}",
            f"情感：{self.relationship_status}",
        ]
        return "\n".join(parts)


def generate_facts(rng: random.Random, birth_date: datetime.date,
                   family_class: str = "普通", family_atmosphere: str = "温暖",
                   current_age: int = 20) -> Facts:
    """从种子派生她的硬事实（与 V3 先在条件同一视角；在演化之前调用）。
    """
    # 城市（出生地 + 现在城市；可能迁移，但 MVP 先用同一省的不同城市/或同城）
    prov, city = rng.choice(CITIES)
    # 现在城市：可能迁移到另一个城市（概率 40%），否则同城
    if rng.random() < 0.4:
        prov2, city2 = rng.choice(CITIES)
        if prov2 != prov:
            current_city = city2
        else:
            current_city = city
    else:
        current_city = city

    # 家庭：阶层 → 父母职业；氛围 → 家庭结构；兄弟姐妹（独生权重高，2000s 独生子女政策）
    parents = rng.choice(FAMILY_CLASS_TO_PARENTS.get(family_class, FAMILY_CLASS_TO_PARENTS["普通"]))
    structure = rng.choice(FAMILY_ATMOSPHERE_STRUCTURE.get(family_atmosphere, ["双亲"]))
    siblings = 0 if rng.random() < 0.7 else rng.randint(1, 2)   # 独生为主

    # 求学/工作/生活：由年龄决定（20-26 岁：在读大学/应届/工作1-3年）
    age = current_age
    school_type = rng.choice(SCHOOL_TYPES)
    major = rng.choice(MAJORS)
    interests = tuple(rng.sample(INTEREST_POOL, k=min(3, len(INTEREST_POOL))))
    keeps = rng.choice(KEEPS_POOL)
    residence = rng.choice(RESIDENCE_POOL)
    if age <= 21:
        education_current = f"在读大学（{birth_date.year + 18}年前后入学）"
        job = "暂无（在读学生）"
        residence = "学校宿舍"
        relationship_status = rng.choice(["单身", "单身", "单身", "有过一段"])
    elif age <= 23:
        education_current = "本科毕业"
        job = rng.choice(JOB_POOL_YOUNG)
        residence = "合租的小单间"
        relationship_status = rng.choice(["单身", "单身", "有过一段", "有过一段"])
    else:
        education_current = "本科毕业"
        job = rng.choice(JOB_POOL_MATURE)
        residence = "合租的小单间"
        relationship_status = rng.choice(["单身", "有过一段", "恋爱中"])

    return Facts(
        birth_place_city=city,
        birth_place_province=prov,
        current_city=current_city,
        family_class=family_class,
        parents_job=parents,
        siblings=siblings,
        family_structure=structure,
        school_type=school_type,
        education_current=education_current,
        major=major,
        job=job,
        working_city=current_city,
        residence=residence,
        interests=interests,
        keeps=keeps,
        relationship_status=relationship_status,
    )


# ── 事实序列化（结构层必需：相遇后事实以"快照"持久化，不再随年龄重生成漂移）──
_FACT_FIELDS = (
    "birth_place_city", "birth_place_province", "current_city",
    "family_class", "siblings", "family_structure",
    "school_type", "education_current", "major",
    "job", "working_city", "residence", "keeps", "relationship_status",
)


def facts_to_dict(facts: Facts) -> dict:
    """Facts → 可 JSON 序列化的 dict（tuple → list）。"""
    d = {k: getattr(facts, k) for k in _FACT_FIELDS}
    d["parents_job"] = list(facts.parents_job or ("", ""))
    d["interests"] = list(facts.interests or ())
    return d


def facts_from_dict(d: dict) -> Facts:
    """dict → Facts（tuple 字段还原为 tuple）。"""
    pj = tuple(d.get("parents_job") or ())
    parents_job = (pj + ("", ""))[:2]
    return Facts(
        **{k: d.get(k, "") for k in _FACT_FIELDS},
        parents_job=parents_job,
        interests=tuple(d.get("interests") or ()),
    )
