"""V3 生命引擎（engine）—— 非线性动力学 + 世界反馈 + 事件涌现。

对应设计 15（线A）的"设计主要件"：
1. 世界反馈：事件强度 = 投入 × 世界响应 r × 情境系数 —— 世界既支持也打击（r 有正有负、会起伏）。
2. 非线性项：S_{t+1} = S_t + α(P-S_t) + β·tanh(k·ΔS_t) + ω_t
   - tanh 饱和 → 存在非线性 → 对初始条件的敏感依赖（混沌）有了可能的机制；
   - 微小差异经多次迭代可能被放大 → 近种子 → 轨迹分离。
3. 事件涌现：不再"预排哪个年龄发生什么"，而是每步由状态(行为)×世界响应 动态决定
   "哪个情境最活跃"，由此"长出"事件序列（不同种子 → 不同人生事件）。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..v2.state import StateVector, DIM_NAMES
from . import world as W


@dataclass
class LifeStep:
    age: int
    domains: list[tuple[str, float]]   # 这一步活跃的情境域及其权重（涌现）
    state: StateVector
    delta: StateVector                 # 事件脉冲 ΔS
    event_note: str
    is_anchor: bool
    is_major: bool = True              # True=大事年（有事件/成锚点）；False=平凡年（仅日常微扰）
    year: int | None = None            # 具体年份（出生日期+年龄推算，展示用）


class EvolutionEngine:
    """非线性演化引擎。"""

    def __init__(self, rng: random.Random,
                 alpha: float = 0.05,       # 回归基线速率
                 beta: float = 0.55,        # 事件脉冲增益
                 k: float = 3.0,            # 非线性饱和强度（tanh 斜率）
                 noise: float = 0.01,       # 随机扰动
                 target_age: int = 30,
                 step_years: int = 1,       # 演化步长（V3 从 3 年细化为 1 年 = 时间点更细腻）
                 chaos_r: float = 3.9,      # 混沌内芯 Logistic 参数（>3.57 即混沌区）
                 chaos_c0: float = 0.4,     # 混沌内芯初值（= 初始条件；种子决定其微扰）
                 chaos_substeps: int = 5,   # 混沌内芯每步迭代次数（快节奏内在脉动→低频人生事件）
                 family_class: str | None = None,  # V5 同源：家庭阶层（影响"金钱/生计"叙事）
                 chaos_dims: int = 3,       # A：多维耦合混沌（维度数；≥2 时维度互相耦合）
                 chaos_coupling: float = 0.06,  # A：维度间耦合强度
                 chaos_gamma: float = 0.02):    # B（降级）：混沌耦合项增益——极弱（混沌通过 A 调制命运、
                                                 # C 证明敏感；"她的人格波动"由经历/世界驱动，非混沌数值）
        self.rng = rng
        self.alpha = alpha
        self.beta = beta
        self.k = k
        self.noise = noise
        self.target_age = target_age
        self.step_years = step_years
        self.chaos_r = chaos_r
        self.chaos_gamma = chaos_gamma
        self.family_class = family_class
        self.chaos_c = chaos_c0
        self.chaos_dims = chaos_dims
        self.chaos_coupling = chaos_coupling
        # A：多维混沌状态（chaos_c 为第 0 维；其余维度由种子派生）
        self.chaos_vec = [chaos_c0] + [0.4 + (i * 0.13) % 0.2 for i in range(1, chaos_dims)]
        self.chaos_substeps = chaos_substeps
        self.steps: list[LifeStep] = []
        self._used_narratives: set[str] = set()   # 这条人生已用过的叙事（去重用）
        self._domain_streak: dict[str, int] = {}  # 每个领域连续被选中的次数（惩罚用）

    # ── 主线：让世界"活"起来 + 让"事件"涌现 ──
    def run(self, state0: StateVector, baseline: StateVector, world: W.WorldState) -> list[LifeStep]:
        """演化一生。每一步：
        1) 读世界响应（起伏中）；2) 从状态算出"每个情境的有活跃度"（行为）；
        3) 选/混合活跃情境 → 事件脉冲；4) 非线性演化；5) 世界自身演化一步。
        """
        S = state0
        raw_steps: list[LifeStep] = []
        for age in range(0, self.target_age + 1, self.step_years):
            # 混沌内芯先走一步（敏感依赖源；它决定"命运的偏向"）
            self._chaos_step()
            bias = self._chaos_bias()
            # ── 判定"大事年 vs 平凡年"──
            # 世界响应峰值 |r| 足够大（顺/逆风显著）→ 大事年；否则平凡年（日常被消化）。
            peak_r = max(abs(r) for r in world.responses.values()) if world.responses else 0.0
            is_major = peak_r >= 0.60 or abs(bias) >= 0.90

            if is_major:
                # 大事年：正常事件回路（生成事件 → 脉冲 → 叙事）
                actives = self._active_domains(S, world, bias, age)
                if actives:
                    main = actives[0][0]
                    for d in list(self._domain_streak.keys()):
                        self._domain_streak[d] = 0
                    self._domain_streak[main] = self._domain_streak.get(main, 0) + 1
                delta = self._delta_from_world(S, world, actives, chaos_bias=bias)
                note = self._note(age, actives, delta, world)
            else:
                # 平凡年：微小日常扰动（状态几乎不动），无事件叙事 → 生活片段
                actives = []
                delta = StateVector(*[self.rng.uniform(-0.012, 0.012) for _ in range(6)])
                note = self._mundane_note(age)

            omega = self._omega()
            S_next = self._step(S, baseline, delta, omega)
            raw_steps.append(LifeStep(age=age, domains=actives, state=S, delta=delta,
                                      event_note=note, is_anchor=False, is_major=is_major))
            S = S_next
            world.step(self.rng)   # 世界也演化一步（运势漂移）
        # 锚点判定（相对显著）：只在"大事年"里按 delta 幅度排名取前 30% 为锚点。
        major_deltas = [max(abs(v) for v in st.delta.as_list()) for st in raw_steps if st.is_major]
        if major_deltas:
            sorted_deltas = sorted(major_deltas, reverse=True)
            cutoff_idx = max(0, int(len(sorted_deltas) * 0.3) - 1)
            cutoff = sorted_deltas[cutoff_idx] if cutoff_idx < len(sorted_deltas) else 0.0
            for st in raw_steps:
                if st.is_major:
                    st.is_anchor = max(abs(v) for v in st.delta.as_list()) >= cutoff and cutoff > 0.05
        self.steps = raw_steps
        return self.steps

    # ── 平凡年生活片段（无大事时的"在过日子"质感）──
    def _mundane_note(self, age: int) -> str:
        """平凡年：一句淡淡的日常，让时间线像真正在生活（不固化、不成认识）。"""
        pool = [
            f"{age}岁，这一年平平淡淡，她像往常一样过完了",
            f"{age}岁，没什么特别的事，日子很安静",
            f"{age}岁，她忙着生活里的小事，没留下什么大记忆",
        ]
        return self.rng.choice(pool)

    # ── 混沌内芯（A：多维耦合 Logistic——维度互相影响，命运更多维度分岔）──
    def _chaos_step(self) -> None:
        """混沌内芯迭代：多维耦合 Logistic 映射，快速迭代 chaos_substeps 次。

        A 升级：从 1 维改为 chaos_dims 维**耦合**映射——
          c_i' = r·c_i(1-c_i) + coupling·(c_{i+1} - c_{i-1})   （维度互相耦合，各自混沌且互影响）
        这样"内在脉动"是多维的（不只是单一朝向），"
        近种子→不同人生"的分岔更多样（不同维度不同步分解）。
        """
        r = self.chaos_r
        cp = self.chaos_coupling
        vec = self.chaos_vec
        for _ in range(self.chaos_substeps):
            nv = []
            for i in range(len(vec)):
                # 耦合：与相邻维度的差（让维度互相影响，而非独立）
                left = vec[(i - 1) % len(vec)]
                right = vec[(i + 1) % len(vec)]
                couple = cp * (right - left)
                new = r * vec[i] * (1.0 - vec[i]) + couple
                nv.append(max(0.0, min(1.0, new)))   # 夹到 [0,1]
            vec[:] = nv
        self.chaos_c = vec[0]   # 保持兼容（第 0 维）
        self.chaos_vec = vec

    def _chaos_bias(self) -> float:
        """把混沌向量映射到 [-1,1]（多维平均：bias 是"内在倾向的多维合成"）。"""
        avg = sum(self.chaos_vec) / len(self.chaos_vec)
        return avg * 2.0 - 1.0

    # ── 动力学（非线性） ──
    def _step(self, S: StateVector, P: StateVector, delta: StateVector, omega: StateVector) -> StateVector:
        """S_{t+1} = S_t + α(P-S_t) + β·tanh(k·ΔS) + ω + **混沌耦合项（B）**

        B 升级：混沌直接耦合进状态演化——她的人格状态本身混沌波动
        （不只"命运走向"敏感，是"她此刻的状态"也敏感依赖）。
        混沌项：C_dim = γ · tanh(δ · chaos_bias)（随混沌内芯波动，写进状态）。
        """
        regress = S.diff(P).scale(-self.alpha)
        puls = StateVector(*(math.tanh(self.k * d) * self.beta for d in delta.as_list()))
        # B：混沌耦合项（状态演化含混沌——personality 状态本身混沌，且围绕基线波动）
        cha = self._chaos_coupling_term() if hasattr(self, "chaos_vec") else None
        nxt = S.add(regress).add(puls).add(omega)
        if cha is not None:
            nxt = nxt.add(cha)
        return nxt.clamp()

    def _chaos_coupling_term(self) -> StateVector:
        """混沌耦合项（B·降级）：极弱的平均 0 扰动。

        决策（诚实）：B（混沌直接进状态）曾反复调不好（推极端/回归抵消/逻辑别扭），
        且收益存疑——"她的人格波动"本该来自**经历/世界**（真实），而非混沌数值。
        故降级：γ=0.02（几乎不推动状态），混沌主要通过 **A（调制命运）+ C（敏感依赖）** 起作用；
        此项仅保留"微扰动"通道（不增加极端游走风险）。
        """
        g = getattr(self, "chaos_gamma", 0.02)
        vec = self.chaos_vec
        biases = [v * 2.0 - 1.0 for v in vec]
        mean = sum(biases) / len(biases)
        vals = [0.0] * len(DIM_NAMES)
        for i in range(min(6, len(biases))):
            vals[i] += g * math.tanh(2.0 * (biases[i] - mean))
        return StateVector(*vals)

    # ── 事件涌现（替代"预排"）──
    def _active_domains(self, S: StateVector, world: W.WorldState, bias: float = 0.0,
                        age: int = 30) -> list[tuple[str, float]]:
        """当前状态 + 世界响应 + 混沌内芯调制 + 人生阶段闸门 → 哪些情境"特别活跃"。

        活跃度 = 投入(d) × |世界响应 r(d)| × 混沌调制(d, bias) × 连续同领域惩罚(d)
        - 混沌调制：bias>0 偏"主动/向外"领域（未来/工作/表达自我），bias<0 偏"防御/向内"领域（信任/归属/亲密）。
        - 连续同领域惩罚：某领域连续被选中的次数越多，活跃度越衰减 → 人生主题会流动切换，
          避免"一生只围绕一个领域打转"。
        - 人生阶段闸门：`can_domain_happen(d, age)` 允许的领域才参与 → 幼年不会发生"工作与生计"。
        - 混沌内芯通过这里改变"事件序列" → 不同微扰 → 不同命运走向（敏感依赖的传递路径）。
        """
        scores = []
        for d in W.DOMAINS:
            if not W.can_domain_happen(d, age):   # 年龄闸门
                continue
            invested = W.effective_investment(S, d)
            r = world.responses.get(d, 0.0)
            act = invested * abs(r)
            # 混沌调制
            if bias >= 0:
                if d in ("未来", "工作与生计", "表达自我"):
                    act *= (1.0 + 0.5 * bias)
            else:
                if d in ("信任", "归属", "亲密关系"):
                    act *= (1.0 + 0.5 * (-bias))
            # 连续同领域惩罚：被连续选中越多，衰减越强（1 → 1/2 → 1/3 ...）
            streak = self._domain_streak.get(d, 0)
            act *= 1.0 / (1.0 + streak)
            scores.append((d, act))
        # 只留"活跃度 > 0 且排名靠前"的情境（保留 top-2，形成"这一段时间的主线"）
        scores.sort(key=lambda x: x[1], reverse=True)
        top = [s for s in scores if s[1] > 0.05][:2]
        if not top:
            # 全平静：取最活跃但很弱的情境，避免全空（可能返回空列表 = 平静）
            top = scores[:1] if scores else []
        return top

    def _delta_from_world(self, S: StateVector, world: W.WorldState, actives,
                          chaos_bias: float = 0.0) -> StateVector:
        """把活跃情境的"事件强度"合并成一个脉冲向量，并**连续**叠加混沌调制。

        关键：混沌 bias 不是只调"排序"，而是**连续**缩放事件强度 →
        微扰直接进入连续数值 ΔS → 再进入状态 → 敏感依赖才真的传递。
        """
        vals = [0.0] * len(DIM_NAMES)
        for d, act in actives:
            ev = W.event_delta(S, world, d)
            # 混沌连续调制：bias 缩放该事件的强度（乘性），微扰 → 连续变化
            scale = 1.0 + 0.6 * chaos_bias
            for i, v in enumerate(ev):
                vals[i] += v * scale
        # 再加一个"混沌自身的直接脉冲"：让 c 的微扰直接进入状态（另一条连续路径）。
        # 增强（0.05→0.12）：世界大事件变稀有后，混沌内芯是敏感依赖的主载体，
        # 必须通过"独立于世界事件"的通道把微扰注入状态（否则被日常和回归项衰减掉）。
        vals[3] += 0.12 * chaos_bias      # 自我价值维度
        vals[4] += 0.12 * chaos_bias      # 信任维度
        return StateVector(*vals)

    def _omega(self) -> StateVector:
        return StateVector(*(self.rng.uniform(-self.noise, self.noise) for _ in range(6)))

    @staticmethod
    def _is_anchor(delta: StateVector) -> bool:
        mag = max(abs(v) for v in delta.as_list())
        return mag >= 0.10

    def _note(self, age: int, actives, delta: StateVector, world=None) -> str:
        """把这一步渲染成"一件具体的事"（用世界叙事 + 主事件的顺/逆风方向）。"""
        if not actives:
            return f"{age}岁，一段平静的日子"
        # 主情境（活跃度最高的那个）
        main_domain = actives[0][0]
        # 主事件方向 = 世界运势 r × 该领域代表性维度的系数符号。
        # 只取"主事件自身"的方向，不受其他领域对冲干扰 → 叙事与主事件因果一致
        # （如：信任领域逆风 → 被背叛叙事；亲密关系顺风 → 被接纳叙事）。
        r_main = world.responses.get(main_domain, 0.0) if world is not None else 0.0
        coeff = W.DOMAIN_COEFF.get(main_domain, (0.0,) * 6)
        # 代表性维度 = 系数绝对值最大的那个
        rep_idx = max(range(len(coeff)), key=lambda i: abs(coeff[i]))
        favorable = (r_main * coeff[rep_idx]) >= 0.0
        return W.render_event(main_domain, age, favorable,
                              rng=self.rng, used=self._used_narratives,
                              family_class=getattr(self, "family_class", None))

    # ── C：数学严谨性——估算最大 Lyapunov 指数（>0 即混沌敏感）──
    @staticmethod
    def est_lyapunov(r: float, c0: float = 0.4, steps: int = 2000,
                     dims: int = 1, coupling: float = 0.0) -> float:
        """估算多维耦合 Logistic 系统的最大 Lyapunov 指数（数值法）。

        方法：跑主轨道 + 一条近轨（初始差 1e-6），每步记录 ln(距离比)，
        平均后得到 λ（>0 = 敏感依赖，= 混沌；≈0 = 边缘；<0 = 稳定）。
        dims>1 时用 '**近轨也耦合演化**'，表征"整体系统"的敏感度。
        """
        # 主轨道 + 近轨道（多维）
        def step_once(vals, r, cp):
            nv = []
            for i in range(len(vals)):
                left = vals[(i - 1) % len(vals)]
                right = vals[(i + 1) % len(vals)]
                couple = cp * (right - left)
                new = r * vals[i] * (1.0 - vals[i]) + couple
                nv.append(max(0.0, min(1.0, new)))
            return nv

        main = [c0] + [0.4 + (i * 0.13) % 0.2 for i in range(1, dims)]
        near = [v + 1e-6 for v in main]
        eps = 1e-6
        total = 0.0
        count = 0
        for _ in range(steps):
            main = step_once(main, r, coupling)
            near = step_once(near, r, coupling)
            # 距离
            dist = max(abs(m - n) for m, n in zip(main, near))
            # 归一化（避免发散）：把近轨拉回 eps 距离，记录放大比
            if dist > 0:
                ratio = dist / eps
                total += math.log(ratio)
                count += 1
                # 重新归一化近轨
                k = eps / dist if dist > 0 else 1.0
                near = [n + (m - n) * (1 - k) for m, n in zip(main, near)]
        return total / count if count else float("nan")
