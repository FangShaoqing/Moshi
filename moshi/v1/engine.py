"""V1 生命引擎（engine）—— 种子 + 先在条件生发 + L2 推进器（六环节） + 混沌扰动。

对应设计：
- 04/11：种子只含"时代锚"，先在条件由系统在合法状态格内生发，非造物主设定。
- 12：L2 因果推进器六环节（①欲望/冲动 内主 → ②外生冲击 外辅 → ③事件E → ④后果C → ⑤反哺ΔS → ⑥推进）。
- 10：确定性混沌用"种子+小扰动经事件累积放大"近似，同种子→同一人，近种子→不同人生。
- 14：ΔS 产物 = Belief（认识+强度），非标签条件式。

实现要点：
- 用一个**确定性 PRNG**（Random(seed)）注入每一步的"微扰”。
- "先在条件"由种子的一次抽取决定；之后 L2 每一步也按 PRNG 抽取，形成**路径依赖**。
- 因为每一步都依赖前面，种子一微扰 → 之后链条全不同 → 确定性混沌的敏感依赖。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from . import world as W
from ..belief import Belief


# ─────────────────────────────────────────────────────────────
# 先在条件（由系统生发，非造物主设定）
# ─────────────────────────────────────────────────────────────

@dataclass
class Preconditions:
    """先在条件 = 系统在合法状态格内生发的、高杠杆的因果起点。"""
    birth_place: str
    birth_place_hint: str
    family_class: str
    family_class_hint: str
    family_atmosphere: str
    family_atmosphere_hint: str
    birth_year: int

    def describe(self) -> str:
        return (f"生于{self.birth_year}，{self.birth_place}（{self.birth_place_hint}），"
                f"家庭{self.family_class}（{self.family_class_hint}），"
                f"家庭氛围{self.family_atmosphere}（{self.family_atmosphere_hint}）")


def generate_preconditions(rng: random.Random, current_year: int, target_min_age: int, target_max_age: int) -> Preconditions:
    """从合法状态格（候选池）内生发先在条件。
    注意：造物主不指定，这里随机从候选池选；时代锚由 current_year - 目标年龄区间倒推。
    """
    place = rng.choice(W.BIRTH_PLACES)
    cls = rng.choice(W.FAMILY_CLASSES)
    atm = rng.choice(W.FAMILY_ATMOSPHERES)
    age = rng.randint(target_min_age, target_max_age)
    birth_year = current_year - age
    return Preconditions(
        birth_place=place["name"],
        birth_place_hint=place["hint"],
        family_class=cls["name"],
        family_class_hint=cls["hint"],
        family_atmosphere=atm["name"],
        family_atmosphere_hint=atm["hint"],
        birth_year=birth_year,
    )


# ─────────────────────────────────────────────────────────────
# L2 推进器：六环节一步
# ─────────────────────────────────────────────────────────────

@dataclass
class StepResult:
    """推进器"一步"的产物。"""
    event_label: str            # 事件的简要描述（③）
    event_domain: str           # 事件所属情境域
    new_beliefs: list[Belief]   # ⑤反哺出的认识（可能 0 条）
    timestamp: int              # 当前年龄


class LifeEngine:
    """L2 因果推进器。每一步从当前状态推出下一个事件并反哺认识。"""

    def __init__(self, rng: random.Random, current_year: int = 2026, target_age: int = 30):
        self.rng = rng
        self.steps: list[StepResult] = []
        self.current_year = current_year
        self.target_age = target_age
        self._drift = 0.0
        self._belief_seq = 0
        self._person = None

    def run(self, person, precondition: Preconditions) -> list[StepResult]:
        """从出生推进到"现在"（current_year），逐年龄生成一段人生。
        这里为了 V1 最小化，用"年龄步进 + 每步决定是否发生'大事'（锚点位置）"来近似 L2。
        真实系统会细走每一时刻；V1 走"关键年龄段"，已能体现混沌敏感依赖。
        """
        for age in range(5, self.target_age + 1, 5):   # 从 5 岁起，每 5 岁一个采样点（V1 简化）
            result = self._step(person, precondition, age)
            self.steps.append(result)
        return self.steps

    # ---- 六环节（V1 简化为一个可读的"事件生成 + 认识反哺"）----
    def _step(self, person, precondition: Preconditions, age: int) -> StepResult:
        # ①/②：决定这一站发生"哪个领域"的事（内主+外辅：主要来自状态，少量来自随机冲击）
        # V1：用一个随机抽取 + 先在条件"拉偏"（贫寒优先工作/金钱，温暖优先自我价值/归属等）
        domain = self._choose_domain(precondition, age)

        # ③：生成具体事件描述（V1 用候选文案，真实系统由大模型在合法格内填充）
        event_label = self._render_event(domain, precondition, age)

        # ④后果/⑤反哺：从"领域→认识倾向池"里挑一条认识，按扰动决定强度
        self._person = person
        self._belief_seq += 1
        new_belief = self._form_belief(domain, event_label, age)
        if new_belief is not None:
            person.add_belief(new_belief)
            return StepResult(event_label=event_label, event_domain=domain,
                              new_beliefs=[new_belief], timestamp=age)
        return StepResult(event_label=event_label, event_domain=domain,
                          new_beliefs=[], timestamp=age)

    def _choose_domain(self, precondition: Preconditions, age: int) -> str:
        """内主+外辅地选"哪一领域发生大事"。受先在条件拉偏（高杠杆放大）。"""
        # 基础分布（V1 均匀，真实系统由状态生发）
        weights = {d: 1.0 for d in W.EVENT_DOMAINS}
        # 先在条件拉偏：家庭/氛围让某些领域更可能"出大事"
        if precondition.family_class in ("贫困",):
            weights["工作与生计"] += 3.0
            weights["金钱"] += 2.0
        if precondition.family_class in ("富足",):
            weights["未来"] += 2.0
            weights["自我价值"] += 1.5
        if precondition.family_atmosphere in ("温暖",):
            weights["自我价值"] += 1.5
            weights["归属"] += 1.0
        if precondition.family_atmosphere in ("动荡", "紧张"):
            weights["信任"] += 2.0
            weights["亲密关系"] += 1.5
        # 年龄拉偏：早年更可能发生在家庭/自我价值；成年后更多工作/亲密
        if age <= 10:
            weights["自我价值"] += 1.5
            weights["归属"] += 1.0
        else:
            weights["工作与生计"] += 1.0
            weights["亲密关系"] += 1.0
        # 用权重随机抽
        return self._weighted_choice(weights)

    def _render_event(self, domain: str, precondition: Preconditions, age: int) -> str:
        """拼出"这件大事"的具体描述（真实系统由大模型填充；V1 用规则生成具体质感）。
        尽量让"先在条件 + 年龄 + 领域"决定走向，避免抽象占位。"""
        place = precondition.birth_place
        cls = precondition.family_class
        atm = precondition.family_atmosphere

        events: dict[str, list[str]] = {
            "信任": [
                f"{age}岁，在{place}，{cls}的家庭里发生了一次让她对'信任人'这件事彻底动摇的事",
                f"{age}岁，身边一个亲近的人（{atm}氛围长大）做出了一件让她不敢再轻易托付的事",
            ],
            "亲密关系": [
                f"{age}岁，她第一次真正走近一个人，却因为{atm}长大的影响，靠近了又想逃",
                f"{age}岁，一段她以为能靠得住的关系，最终以一次让她伤心的收场告终",
            ],
            "工作与生计": [
                f"{age}岁，{cls}的家境让她不得不早早面对{place}的生存压力，开始为生计奔波",
                f"{age}岁，在{place}，她第一次为了一份能糊口的工作拼尽全力",
            ],
            "金钱": [
                f"{age}岁，{cls}的家底加上{place}的现实，让她第一次真切体会到'钱'的分量",
                f"{age}岁，因为钱，她被迫做了一次不想做的选择",
            ],
            "自我价值": [
                f"{age}岁，{atm}的家庭氛围让她第一次怀疑'我是不是不值得被好好对待'",
                f"{age}岁，有那么一次，她觉得自己真的可以，但很快又不敢信了",
            ],
            "归属": [
                f"{age}岁，在{place}，她总觉得自己不属于这里，可又不知道哪里才是家",
                f"{age}岁，她第一次尝到'被一个地方接住'是什么感觉",
            ],
            "未来": [
                f"{age}岁，{cls}的出身让她第一次看清：理想和活下去是两回事",
                f"{age}岁，在{place}，她暗暗许下一个自己都未必敢信的念头",
            ],
            "表达自我": [
                f"{age}岁，{atm}长大的她，又一次把想说的话咽了回去",
                f"{age}岁，她第一次鼓起勇气说出心里话，却没被接住",
            ],
        }
        pool = events.get(domain, [f"{age}岁，在「{domain}」上发生了一件大事"])
        return self.rng.choice(pool)

    def _form_belief(self, domain: str, event_label: str, age: int) -> Belief | None:
        """⑤反哺：从该领域的"倾向候选池"挑一条认识，按扰动定强度。
        为增厚度，优先挑选"尚未形成过"的倾向（避免人格单调重复）。"""
        pool = W.DOMAIN_TENDENCY_POOL.get(domain)
        if not pool:
            return None
        # 收集已形成的倾向（tendency），用于去重
        used = set(b.tendency for b in self._person.beliefs if b.domain == domain)
        fresh = [p for p in pool if p["tendency"] not in used]
        candidate_pool = fresh if fresh else pool       # 都形成过则允许重复
        pick = self.rng.choice(candidate_pool)
        strength = self._bounded(self.rng.uniform(0.35, 0.9) + self._drift)
        # 小幅记录扰动，"扰动累积"是混沌的本体：这一步的 strength 受上一步影响（这里简单累加）
        self._drift += (strength - 0.6) * 0.02
        return Belief(
            id=f"e{age}::{domain}::{self._belief_seq}",
            cause=event_label,
            domain=domain,
            tendency=pick["tendency"],
            attribution=pick["attribution"],
            strength=strength,
            salience=0.5,
            formed_at=age,
        )

    @staticmethod
    def _bounded(x: float) -> float:
        return max(0.0, min(1.0, x))

    def _weighted_choice(self, weights: dict[str, float]) -> str:
        """按权重随机抽。必须用 self.rng，才能保证"同种子 → 同一人"可复现。"""
        total = sum(weights.values())
        r = self.rng.random() * total
        acc = 0.0
        for k, v in weights.items():
            acc += v
            if r <= acc:
                return k
        return list(weights.keys())[-1]
