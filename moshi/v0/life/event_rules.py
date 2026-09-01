"""事件 → 认识映射（V0 硬编码规则）。

在完整系统中，这里的"映射"会由 L2 因果推进器 + ΔS 反哺（丙）自动完成；
V0 用一套可读的硬编码规则，验证"从经历长出的认识"是否真的非标签、有厚度、可矛盾。
"""

from __future__ import annotations

from ..belief import Belief
from ..person import Person


# 一个"经历"的极简表示（V0 手写）。真实系统中它由 L2 生发。
# 每个经历：id, 年龄, 简述, 是否外生冲击, 以及它"沉淀出的认识"的种子信息。
# 注意：mapped_beliefs 这里是手写的"这条经历让她学到了什么"，模拟的是
# "大模型在合法格内、受控 domain 下填写的 tendency/attribution"。

EVENT_TO_BELIEF_RULES: dict[str, list[dict]] = {
    # 1. 早期：一个被信任的人背叛了她 → 建立在"信任"上的强烈认识
    "trust_betrayed_at_16": [
        {
            "domain": "信任",
            "tendency": "先留三分，不轻易全盘托付",
            "attribution": "因为最信任的人也能转身背叛，所以'交出去'变得很危险",
            "strength": 0.75,
            "salience": 0.5,
            "tension_hint": "想靠近",
        },
        {
            "domain": "亲密关系",
            "tendency": "会先试探，确认对方可靠才慢慢亲近",
            "attribution": "怕再受伤，所以选择'慢一点再交心'",
            "strength": 0.6,
            "salience": 0.4,
            "tension_hint": "渴望亲密",
        },
    ],
    # 2. 家庭贫寒 → "安稳要靠自己挣"
    "grew_up_poor": [
        {
            "domain": "工作与生计",
            "tendency": "把安稳当作必须靠自己挣来的东西，而不是理所当然",
            "attribution": "从小看她为钱发愁，明白'安稳'要付出，不是天生就有的",
            "strength": 0.7,
            "salience": 0.6,
        },
        {
            "domain": "金钱",
            "tendency": "对钱谨慎、会为未来留后路，不轻易挥霍",
            "attribution": "缺过，所以懂得'手里有粮，心里不慌'",
            "strength": 0.65,
            "salience": 0.5,
        },
    ],
    # 3. 一次被温柔接纳 → 滋生出"也许有人真的在乎我"的微光
    "was_gently_accepted_at_20": [
        {
            "domain": "自我价值",
            "tendency": "开始相信'也许我值得被好好对待'，但不敢完全信",
            "attribution": "有个人没有因为她的过去而离开，让她第一次觉得'我可能也配'",
            "strength": 0.5,
            "salience": 0.4,
            "tension_hint": "我不配",
        },
        {
            "domain": "归属",
            "tendency": "会对那个接纳她的人产生依赖，但会克制不索取太多",
            "attribution": "怕一索取就把这份难得的好感吓跑",
            "strength": 0.45,
            "salience": 0.5,
        },
    ],
    # 4. 为生计辍学早早打工 → 理想与现实的对撞
    "dropped_out_to_work_at_17": [
        {
            "domain": "未来",
            "tendency": "把'理想'和'活下去'分开想，先活着再说理想",
            "attribution": "没资格只谈理想，得先有饭吃，这是她学会的生存逻辑",
            "strength": 0.68,
            "salience": 0.55,
            "tension_hint": "不甘心",
        },
        {
            "domain": "表达自我",
            "tendency": "把很多心里话憋着，怕说出来是负担",
            "attribution": "习惯了把苦咽下去，不想让人为难",
            "strength": 0.55,
            "salience": 0.45,
        },
    ],
}


def apply_event(person: Person, event_id: str, age: int, narrative: str) -> None:
    """把一个经历喂给这个人，依据硬编码规则沉淀出若干条认识。"""
    rules = EVENT_TO_BELIEF_RULES.get(event_id)
    if not rules:
        print(f"[跳过] 无规则：{event_id}")
        return

    print(f"\n── 经历（{age}岁）：{narrative} ──")
    for idx, r in enumerate(rules, 1):
        belief = Belief(
            id=f"{event_id}::b{idx}",
            cause=f"{age}岁，{narrative}",
            domain=r["domain"],
            tendency=r["tendency"],
            attribution=r["attribution"],
            strength=r["strength"],
            salience=r["salience"],
            formed_at=age,
        )
        person.add_belief(belief)
        print(f"  · 沉淀出认识[{belief.id}]：{belief.describe()}")
