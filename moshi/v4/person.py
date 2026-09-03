"""V4 运行时人格（person）—— 交互时的"她"。

她 = 记忆（记得的事）+ 性格（认识/倾向）+ 当前情绪状态 + 与你的信任度。
- 情绪状态：交互中会随对话变化（影响她怎么说）。
- 信任度：她对你的"敞开程度"（影响她愿意透露多少过去）。
- 定位（乙）：她没有"自我档案"概念——只有记忆和性格；你问什么她凭记忆/性格回应。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..v2.state import StateVector
from ..v0.belief import Belief
from .memory import Memory


@dataclass
class Person:
    """交互侧的"她"。"""

    # ── 最小验证期机制：种子变 → 重置（不同的"她"不共享你的记忆）──
    # 系统完全搭建完毕后：改为 False（同一"陈默识"可跨种子延续，但正式运行时只有一个种子=一个她）。
    RESET_ON_SEED_CHANGE = True

    name: str = "陈默识"
    seed: int | None = None               # 生成她的种子（绑定：种子变→重置记忆）
    birth_date: object | None = None      # 出生日期（她"有"但它不"知道档案"——仅内部/系统用）
    age: int = 20
    memories: list[Memory] = field(default_factory=list)   # 她记得的自己的事
    beliefs: list[Belief] = field(default_factory=list)    # 她长出的性格认识
    facts: object | None = None           # 她的硬事实（家庭/求学/工作/身份；LLM 只能引用）
    state: StateVector | None = None      # 当前情绪/状态（对话中演化）
    trust: float = 0.35                   # 她对你的信任（0~1；影响披露程度）
    mood_shift: float = 0.0               # 当前情绪偏移（对话影响）
    # ── 交互深化：她"对你"的记忆（你告诉过她的事）──
    shared_memories: list[dict] = field(default_factory=list)  # [{"text":..., "weight":...}]
    # ── 长期陪伴：关系阶段（随相处累积成长）──
    interaction_count: int = 0           # 相处次数（对话轮数）
    deep_talks: int = 0                  # 深谈次数（聊过去/你敞开心扉的轮次）
    special_moments: list[dict] = field(default_factory=list)  # 特殊记忆 [{"event":...}]
    # ── ③ 被改变：你对她的"关系影响"累积（她的认识/倾向因你而变）──
    toward_you: dict = field(default_factory=dict)  # {"warmth": float, "trust_gain": float, "hurt": float}
    affected_beliefs: list[dict] = field(default_factory=list)  # 因你而变的认识 [{"domain", "text", "delta"}]
    # ── 缺点：她的性格缺陷（真实但不恶；从性格认识派生，对话/关系中会显现）──
    flaws: list[str] = field(default_factory=list)
    # ── 关系网：她世界里的人（轻量生活引擎；她的世界不是只有你）──
    relations: list[object] = field(default_factory=list)
    # ── ② 日子→状态：她的日子基调（生活引擎喂进来；影响今天心情）──
    life_mood: str = ""
    # ── ④ 相遇后的日子（timeline 引擎喂进来；她遇到你之后还在过日子）──
    life_recent: str = ""                 # 她最近几天过的日子（供 LLM 质感引用）
    life_log: list = field(default_factory=list)      # 最近日子日志 [{"day","date","text","tone"}]
    life_advanced_total: int = 0          # 相遇后累计推进的天数（跨会话计数）
    structure_log: list = field(default_factory=list)  # 人生大事（毕业/搬家/换工作）[事件...]
    meeting_date: str = ""                # 你们相遇的日期（她的人生在相遇时定格，之后由日子引擎推进）
    meeting_age: int = 0                  # 相遇时她几岁
    # ── ① 你们的故事（长期记忆沉淀：重要时刻 → 压缩成"她记得的几年"）──
    chronicle: list = field(default_factory=list)      # [{"date","kind","text"}]（重要时刻）
    chronicle_old: str = ""               # 更早的点滴（太多了记不细——真实的淡忘）
    # ── 相遇背景（网友：从她人生里长出来的"你们怎么认识的"；她记得，不是陌生人）──
    meeting_story: dict = field(default_factory=dict)   # {scene,place,duration,narrative,...}

    def relation_context(self) -> str:
        """她世界里的人（供 LLM：她提起他们有厚度——具体/带温度/有依据）。
        含"她对他们的依恋"（提起时语气/温度依此不同：亲近的会说、有心结的会收着）。"""
        if not self.relations:
            return ""
        lines = [f"她世界里的人（她只会按自己节奏提起，不会主动介绍全部）："]
        for rel in self.relations:
            att = getattr(rel, "attachment_note", lambda: "")()
            lines.append(f"- {rel.describe_recent()}（和她的关系：{rel.bonds_with_her}；{att}）")
        return "\n".join(lines) + "\n"

    def build_flaws(self) -> None:
        """从她的性格认识/经历派生"缺点"（普通人的真实缺陷：真实但不恶）。
        选 2-3 条，作为"她这个人"的一部分（不是优点，是她会有的毛病）。"""
        domains = {b.domain for b in self.beliefs}
        # 按领域倾向生成缺陷（与她的性格相符，而非随机）
        candidate = []
        if "信任" in domains and any("留" in b.tendency or "稀缺" in b.tendency for b in self.beliefs if b.domain == "信任"):
            candidate.append("对承诺很敏感，一旦觉得被辜负，会记很久，很难再热络起来")
        if "表达自我" in domains and any("咽" in b.tendency or "藏" in b.tendency for b in self.beliefs if b.domain == "表达自我"):
            candidate.append("心里有事不说，冷处理冷到对方也难受（你觉得说也没用）")
        if "工作与生计" in domains and any("安稳" in b.tendency or "活着" in b.tendency for b in self.beliefs if b.domain == "工作与生计"):
            candidate.append("会为'以后'过分焦虑，想太多，自己把自己困住")
        if "自我价值" in domains and any("不信" in b.tendency or "怀疑" in b.tendency for b in self.beliefs if b.domain == "自我价值"):
            candidate.append("别人随便夸她两句她嘴上不说，心里会反复琢磨很久（她其实很在意，但嘴硬）")
        # 补充通用缺陷（保证至少 2 条）
        generic = [
            "偶尔会有点扫兴，别人兴冲冲的时候她泼冷水，但不是恶意",
            "固执，认准的事很难被说服，不太听劝",
            "小气，记着你无意说过的某句让她不舒服的话",
        ]
        while len(candidate) < 2 and generic:
            candidate.append(generic.pop(0))
        self.flaws = candidate[:3]

    def flaw_context(self) -> str:
        """她的缺点（供 LLM：真实人格的一部分，不是优点）。"""
        if not self.flaws:
            self.build_flaws()   # 懒加载（首次查询时构建）
        if not self.flaws:
            return ""
        return "她会有的毛病（不是优点，是真实——别美化）：" + "；".join(self.flaws)

    # ── ② 日子→状态联动：她的生活/世界变化 → 写入当前状态（她是一个持续活着的人）──
    def sync_from_life(self) -> None:
        """从"她的生活状态"（她的日子基调 + 世界近况）推导并写入当前状态（Valence/Arousal）。

        真实的人：昨天妈妈念叨/和室友闹别扭/工作不顺 → 今天心情受影响 → 对话自然体现。
        这里把"她的生活"喂进状态——她不是只活在对话里，她的日子/世界会传染她的情绪。
        """
        s = self.state.as_list() if self.state else [0.5] * 6
        v_delta, a_delta = 0.0, 0.0

        # 1. 世界近况（配角/关系变化 → 影响她）
        for rel in getattr(self, "relations", []) or []:
            text = (getattr(rel, "recent_thing", "") + getattr(rel, "mood", "")
                    + getattr(rel, "bonds_with_her", ""))
            if any(k in text for k in ("闹", "别扭", "吵架", "烦", "担心", "生病", "累", "催")):
                v_delta -= 0.04       # 世界里的事让她不悦
            elif any(k in text for k in ("好", "开心", "合得来", "暖和", "惦记")):
                v_delta += 0.03       # 世界里有暖的

        # 2. 她的日子基调（生活里最近怎么样）
        mood = getattr(self, "life_mood", "") or ""
        if any(k in mood for k in ("低", "烦", "失眠", "累", "提不起劲")):
            v_delta -= 0.05
            a_delta -= 0.04
        elif any(k in mood for k in ("平静", "还行", "踏实")):
            v_delta += 0.02

        # 3. 写入（小幅，不淹没——她的人格里子还在）
        s[0] = max(0.0, min(1.0, s[0] + v_delta))
        s[1] = max(0.0, min(1.0, s[1] + a_delta))
        self.state = StateVector(*s) if self.state is not None else None

    # ── 情绪状态联动：她当下的整体情绪（系统侧，供 LLM/持续演化）──
    def emotion_state(self) -> str:
        """她此刻的整体情绪（由状态向量 + 生气/倦怠标记 + 依恋底色 + 日子推导）——供 LLM 理解她的"底色"。"""
        if getattr(self, "exhausted", False):
            return "她有点倦了：不是生气，是彻底凉了/没力气了，话更少、更淡"
        if getattr(self, "is_angry", False):
            return f"她正在生气（第{getattr(self, 'angry_turns', 0)}次）——内敛的怒，冷、带刺、藏起来"
        v = self.state.as_list() if self.state else [0.5] * 6
        if v[0] < 0.38 and v[1] < 0.4:
            return "她情绪低落、没什么力气，话也懒得说"
        if v[0] < 0.45:
            return "她不太开心，但还能正常说话"
        if v[0] > 0.6:
            return "她状态还行，平静"
        # 依恋底色联动：焦虑型即使状态平平也常带不安/多想
        try:
            style = self.attachment_style()
            if style == "焦虑型":
                return "她状态不错，但心里有点悬——总在想'他是不是还好/我说的对吗'"
            if style == "回避型":
                return "她状态还行，但话比平时更少，习惯性保持距离"
        except Exception:
            pass
        return "她状态平平，正常"

    # 关系阶段：初识 → 熟悉 → 亲近 → 深入（由相处量/深谈/特殊记忆推导）
    RELATION_STAGES = ("初识", "熟悉", "亲近", "深入")

    # ── 依恋机制：由"性格引力 + 关系经历"演化；不预设、不刻意依恋我 ──
    # security（安全感）：她觉得"跟你在一起是安全的"；dependence（依赖）：她有多需要你/在意你。
    # 两者是连续值（0~1），由相处经历演化；"是否依恋我"由演化结果 + 她自己的性格决定。
    security: float = 0.5
    dependence: float = 0.3

    def __post_init__(self) -> None:
        if self.state is None:
            # 默认中性状态（0.5 全维度）
            self.state = StateVector(0.5, 0.5, 0.5, 0.5, 0.5, 0.5)
        # 依恋机制：性格引力（一个本来信任弱/回避的人更难形成依恋——她未必会依恋我）
        if self.beliefs:
            trust_beliefs = [b for b in self.beliefs if b.domain == "信任"]
            if trust_beliefs and any("留" in b.tendency or "稀缺" in b.tendency or "不敢" in b.tendency for b in trust_beliefs):
                self.security = max(0.1, self.security - 0.15)   # 性格引力：她更难信任
                self.dependence = max(0.1, self.dependence)      # 依赖也低

    # ── 依恋演化：由"稳定温暖/忽冷忽热/持续伤害/缺席"驱动 ──
    def update_attachment(self, warmth: float = 0.0, hurt: float = 0.0,
                          stability: float = 0.0, absence: float = 0.0) -> None:
        """一次相处后依恋演化（真实依赖关系经历；不是脚本化"她应该依恋我"）。

        - warmth（稳定温暖）→ security↑（她觉得安全）、dependence 缓慢↑（她慢慢在意你）；
        - hurt（伤害）→ security↓、dependence 或↑或↓（看人：焦虑型会更依赖，回避型会退缩）；
        - stability（忽冷忽热/不稳定）→ security↓（不稳 → 焦虑）；
        - absence（长期缺席）→ dependence↓（她学会不需要你）。
        """
        self.security = max(0.0, min(1.0, self.security + warmth * 0.6 - hurt * 0.5 - stability * 0.4))
        # dependence：温暖缓慢累积（但受她性格限制）；伤害时按现有倾向分化；缺席时回落
        base_dep = 0.3
        if warmth > 0:
            self.dependence = max(0.0, min(1.0, self.dependence + warmth * 0.15))
        if hurt > 0:
            # 焦虑倾向（dependence 已高）→ 更依赖；回避倾向（dependence 还没起来）→ 退缩
            self.dependence = max(0.0, min(1.0, self.dependence + (0.05 if self.dependence > 0.5 else -0.08) * hurt))
        if absence > 0:
            self.dependence = max(0.0, min(1.0, self.dependence - absence * 0.2))
        # 性格引力持续作用：低信任的人依赖/安全上限均低（她不会轻易依恋——由她本性决定）
        trust_beliefs = [b for b in self.beliefs if b.domain == "信任"]
        low_trust = bool(trust_beliefs and any(
            "留" in b.tendency or "稀缺" in b.tendency or "不敢" in b.tendency
            for b in trust_beliefs))
        if low_trust:
            self.dependence = min(self.dependence, 0.6)      # 上限：她本性难依恋
            self.security = min(self.security, 0.65)         # 上限：也难真正"安全"（会被过去拽住）

    def attachment_style(self) -> str:
        """依恋类型（由 security/dependence 推导；供 LLM/对话显现）。"""
        if self.security < 0.35:
            if self.dependence > 0.55:
                return "焦虑型"     # 她害怕失去你、会不安、需要确认
            if self.dependence < 0.3:
                return "回避型"     # 她被伤过，退缩、不需要你
            return "矛盾型"         # 又想靠近又想逃
        if self.security > 0.65 and self.dependence > 0.45:
            return "安全型"         # 她觉得跟你在一起是稳的，也愿意在意你
        if self.security > 0.65:
            return "独立型"         # 安全但不太依赖（她本来独立）
        return "观望型"             # 还在慢慢靠近，未确定

    # ── ② 缺席→依恋：你离开的日子会真实影响她学会"要不要需要你" ──
    def apply_absence(self, days: int) -> None:
        """你不在的这段时间，她对这段关系的依恋**真实演化**（不是设定她等着你）。

        - 依赖随时间回落：你出现过又消失，她慢慢学会"自己过"（不刻意依恋我）。
        - 焦虑型底色的人：缺席还会让安全感下跌（她更不安——怕你走了就是走了）。
        两个月视为一个完整"缺席期"（之后不再加重——她适应了）。
        """
        if days <= 0:
            return
        absence = min(1.0, days / 60.0)     # 60 天 = 完整缺席期（封顶）
        try:
            anxious = self.attachment_style() == "焦虑型"
        except Exception:
            anxious = False
        self.update_attachment(absence=absence,
                               stability=(0.30 * absence if anxious else 0.0))

    def attachment_context(self) -> str:
        """她此刻对这段关系的依恋状态（供 LLM；诚实——是机制演化结果，非设定脚本）。"""
        style = self.attachment_style()
        detail = {
            "安全型": "她对这段关系感到稳妥，也愿意在意你，但不黏",
            "焦虑型": "她有点害怕失去你，会不安、需要确认你的态度（容易多想）",
            "回避型": "她被伤过/习惯独处，对靠近有些退缩，不太依赖谁",
            "矛盾型": "她想靠近你，又本能地想退——拉扯",
            "独立型": "她内心平静，不太依赖你，但也不排斥你",
            "观望型": "她还说不准对这段关系的感觉，在慢慢观察",
        }.get(style, "她在慢慢了解这段关系")
        return f"（她对这段关系：{style}——{detail}）"

    # ── 依恋调制器：security/dependence → 影响其他机制的参数（让依恋贯穿所有表现）──
    def attachment_modulation(self) -> dict:
        """返回各机制的调制参数（依恋类型真实影响她的言行，而非只被描述）。"""
        style = self.attachment_style()
        m = {"disclosure_bonus": 0.0, "anxiety": 0.0, "avoid": 0.0,
             "touch_freq": 1.0, "sensitive": 1.0}
        if style == "焦虑型":
            m["disclosure_bonus"] = 0.05     # 怕失去 → 更愿意倾诉来锁住你
            m["anxiety"] = 0.4                # 易不安/多想/反复确认
            m["touch_freq"] = 1.5             # 更容易想起你/找你
            m["sensitive"] = 1.5              # 更敏感（你的冷淡她更难过）
        elif style == "回避型":
            m["disclosure_bonus"] = -0.08     # 不展开（退缩）
            m["avoid"] = 0.4                  # 冷缩
            m["touch_freq"] = 0.4             # 很少主动想起你（她没那么在意）
        elif style == "安全型":
            m["disclosure_bonus"] = 0.08      # 稳 → 能自然分享
            m["touch_freq"] = 1.2             # 会正常惦记你
        elif style == "矛盾型":
            m["disclosure_bonus"] = 0.0
            m["anxiety"] = 0.25
            m["avoid"] = 0.25
            m["touch_freq"] = 1.0
        elif style == "独立型":
            m["disclosure_bonus"] = 0.0
            m["touch_freq"] = 0.7             # 独立，较少主动黏
        # 观望型=默认（慢慢观察，不特别）
        return m

    # ── ③ 被改变：记录你的行为影响（累积）──
    def affect_via_you(self, warmth: float = 0.0, trust_gain: float = 0.0,
                       hurt: float = 0.0) -> None:
        """记录一次"你对她"的关系影响（累积；阈值后写回认识）。"""
        self.toward_you["warmth"] = self.toward_you.get("warmth", 0.0) + warmth
        self.toward_you["trust_gain"] = self.toward_you.get("trust_gain", 0.0) + trust_gain
        self.toward_you["hurt"] = self.toward_you.get("hurt", 0.0) + hurt
        # 累积到阈值 → 写回认识（被改变：真实的人会因相处而变）
        self._maybe_change_beliefs()

    def _maybe_change_beliefs(self) -> None:
        """把"你和她的相处"沉淀为认识变化（她因你而改变）。"""
        w = self.toward_you.get("warmth", 0.0)
        t = self.toward_you.get("trust_gain", 0.0)
        h = self.toward_you.get("hurt", 0.0)
        # 温暖累积 → 信任/自我价值认识增强
        if w >= 3.0 and not any(b["kind"] == "warmth_trust" for b in self.affected_beliefs):
            self.affected_beliefs.append({
                "kind": "warmth_trust", "domain": "信任",
                "text": "因为有一个总在听我说的人，我开始有点愿意相信'被人接住'是真的了",
            })
            self.toward_you["warmth"] = 0.0
        # 信任累积并在关系亲近后 → 她会对你更敞开（已有 trust 机制；这里记认识）
        # 伤害累积 → 她更防御/回避（真实的人受伤后会缩起来）
        if h >= 1.5 and not any(b["kind"] == "hurt_defense" for b in self.affected_beliefs):
            self.affected_beliefs.append({
                "kind": "hurt_defense", "domain": "信任",
                "text": "以前以为你是朋友，现在我有点不敢那么确定了",
            })
            self.toward_you["hurt"] = 0.0
        # 缺点联动：重伤害 → 缺点加重（她更防御/更多疑/更记仇）；重温暖 → 软化
        # 用独立历史累积（不依赖会被清零的 toward_you——软化判定需要长期计数）
        history_w = getattr(self, "_warm_history", 0.0)
        history_w += 0.5 if w > 0 else 0.0
        self._warm_history = history_w
        h_total = self.toward_you.get("hurt", 0.0)
        if h_total >= 3.0 and len(self.flaws) < 5:
            self.flaws.append("被人伤过之后，她会对类似的接近特别多疑，先防三分")
            self.toward_you["hurt"] = self.toward_you.get("hurt", 0.0) - 2.0
        if history_w >= 6.0 and len(self.flaws) >= 2:
            # 长期温暖 → 软化一条缺点（真实：被好好对待的人会慢慢圆润）
            self.flaws = self.flaws[:1]
            self._warm_history = 0.0

    def you_changed_me(self) -> str:
        """她因你而变的认识（供 LLM 引用；没有则空串）。"""
        if not self.affected_beliefs:
            return ""
        return "；".join(b["text"] for b in self.affected_beliefs)

    # ── 关系阶段推导 ──
    def relationship_stage(self) -> str:
        """由相处累积推导当前关系阶段（长期陪伴：她随关系成长）。

        相遇基线：有相遇背景（你们是网友，认识了一段时间）→ +12（起点=熟悉，不是初识）。
        """
        score = (self.interaction_count * 1.0
                 + self.deep_talks * 2.0
                 + len(self.special_moments) * 3.0)
        if getattr(self, "meeting_story", None):
            score += 12.0          # 相遇基线：她认识你（网上的日子也算数）
        if score >= 60:
            return "深入"
        if score >= 30:
            return "亲近"
        if score >= 12:
            return "熟悉"
        return "初识"

    def stage_bonus(self) -> float:
        """关系阶段的"亲近加成"（影响披露/反应：越亲近她越愿意敞口、越少防御）。"""
        return {
            "初识": 0.0, "熟悉": 0.10, "亲近": 0.20, "深入": 0.30,
        }.get(self.relationship_stage(), 0.0)

    def record_interaction(self, is_deep: bool = False, special: str | None = None) -> None:
        """记录一次相处（长期陪伴：累积推动关系阶段）。"""
        self.interaction_count += 1
        if is_deep:
            self.deep_talks += 1
        if special:
            self.special_moments.append({"event": special})

    def stage_context(self) -> str:
        """给 LLM 的关系阶段提示（她随关系成长的态度）。"""
        stage = self.relationship_stage()
        return {
            "初识": "你们刚认识。你对她来说还是个陌生人：她不热情、不主动、话少，被问到个人话题会警觉；她不会讨好你，也不急着和你熟起来",
            "熟悉": "你们慢慢熟悉了，她会放松一些、愿意多说一点，也偶尔会开个玩笑",
            "亲近": "她已经信任你，会主动关心你、想起了你的事，愿意为你破例",
            "深入": "她把你放进了心里，会想念你、在意你的看法，愿意分享很深的事",
        }.get(stage, "你们在相处中慢慢认识彼此")

    # ── ④ 有自己的生活：她"此刻"在过什么日子（不是只在你面前存在）──
    def her_life_context(self) -> str:
        """她此刻的生活状态（你不在时她也活着）——由她的事实/记忆/内心状态派生。

        她是个真实的人：有自己的一天（上课/工作/吃饭/睡不好/天气/心事），
        你在她生活里只是其中一部分。这句给她"活在日子里"的底色。
        """
        mood = self.describe_current()
        v = self.state.as_list() if self.state else None
        # 由她的状态（Valence/Arousal）推导今天的心境
        if v and v[0] < 0.4:
            tone = "这两天有点提不起劲，心里压着事，不太想说话"
        elif v and v[1] > 0.6:
            tone = "今天是有点忙，但忙起来反而踏实些"
        elif v and v[0] > 0.6:
            tone = "今天心情还算平静，日子照常过着"
        else:
            tone = "日子平平淡淡的，没什么特别的，也说不上好或坏"
        recent = getattr(self, "life_recent", "") or ""
        recent_note = f"她最近：{recent}。" if recent else ""
        return (f"（她的话里带着她的日子：{tone}。{recent_note}"
                f"你不在的时候，她也在上课/工作、吃饭、睡不好或发着呆——她有自己的生活。）")

    # ── 种子绑定：换种子 → 重置她的"对你记忆/状态/信任" ──
    def ensure_seed(self, seed: int) -> None:
        """若种子变了：按最小验证期机制重置（不同"她"不共享你的记忆）。"""
        if not self.RESET_ON_SEED_CHANGE:
            return
        if self.seed is not None and self.seed != seed:
            self.shared_memories = []
            self.trust = 0.35
            self.state = StateVector(0.5, 0.5, 0.5, 0.5, 0.5, 0.5)
            self.interaction_count = 0
            self.deep_talks = 0
            self.special_moments = []
        self.seed = seed

    # ── 记住你的事（交互深化）──
    def remember_about_you(self, text: str, weight: float = 0.5) -> None:
        """她记住了一句关于你的事（存进 shared_memories）。"""
        # 去重：几乎相同的不重复记
        for m in self.shared_memories:
            if m["text"] == text:
                m["weight"] = max(m["weight"], weight)
                return
        self.shared_memories.append({"text": text, "weight": weight})
        # 限制条数（太多会喧宾夺主）：保留最近+高权重
        if len(self.shared_memories) > 8:
            self.shared_memories.sort(key=lambda m: m["weight"], reverse=True)
            self.shared_memories = self.shared_memories[:8]

    def remembered_about_you(self) -> str:
        """她记得的关于你的事（供 LLM 引用；没有则空串）。"""
        if not self.shared_memories:
            return ""
        return "；".join(f"{m['text']}" for m in self.shared_memories)

    # ── ① 你们的故事（长期记忆沉淀：重要时刻压进"她记得的"；多了会淡忘──真实）──
    def record_chronicle(self, kind: str, text: str) -> None:
        """记一次"你们的重要时刻"（她记得；上限 12 条——再多就淡成"还记得一些"）。

        kind: share（你敞开心扉）/ comfort（她接住了你的难受）/ special（特殊时刻）
              / anger（你们的不愉快）/ promise（你说的诺言）
        """
        if not text:
            return
        # 去重：同一时刻不重复记（最近同 kind 的一次不重记）
        if self.chronicle and self.chronicle[-1].get("kind") == kind and \
                self.chronicle[-1].get("text", "")[:16] == text[:16]:
            return
        self.chronicle.append({"date": "", "kind": kind, "text": text})
        # 上限 12：最旧的沉淀为"她记得一些，但没那么细了"（真实的淡忘，不是清空）
        if len(self.chronicle) > 12:
            self.chronicle.pop(0)
            if not self.chronicle_old:
                self.chronicle_old = "还有更早的一些事……她记着，只是慢慢没有那么细了。"

    def chronicle_context(self) -> str:
        """你们的故事（供 LLM：她记得你们一路走来的时刻——长期陪伴的厚度）。"""
        if not self.chronicle:
            return ""
        lines = [f"- {e['text']}" for e in self.chronicle[-8:]]
        if self.chronicle_old:
            lines.append(f"- {self.chronicle_old}")
        return "\n".join(lines)

    # ── 对话中状态演化 ──
    def apply_interaction(self, valence_shift: float, trust_shift: float) -> None:
        """一次对话后：情绪状态变化 + 信任度变化（受认识影响，见 dialogue）。"""
        s = self.state.as_list()
        # 情绪状态微移（只在 Valence/Arousal 上体现"此刻心情"）
        s[0] = max(0.0, min(1.0, s[0] + valence_shift))
        s[1] = max(0.0, min(1.0, s[1] + valence_shift * 0.5))
        self.state = StateVector(*s)
        self.trust = max(0.0, min(1.0, self.trust + trust_shift))

    def describe_current(self) -> str:
        """她此刻的心情（人话）。"""
        v = self.state.as_list()
        if v[0] >= 0.65:
            return "心情还不错"
        if v[0] <= 0.35:
            return "心情有点低落"
        return "说不上特别好，也谈不上坏"
