"""V4+ 运行时会话（runtime）—— 通道无关的"她"：任何入口发来一句话，她处理、作答、并保持状态。

与 demo 同源（相遇定格 + 日子引擎 + 持久化），但抽象为**单轮服务**：
- 一个种子 = 一个她；状态在 `data/SHE_<seed>/`（跨渠道 / 跨进程 / 跨时间）；
- `Session.on_message(文本)` = demo 对话循环的单轮化（生成 → 效果 → 记住 → 偶尔主动）；
- `Session.tick()` = "她会突然想起你"（需通道支持主动推送）；
- 每次消息后落盘（崩溃安全：她永远记得上一次）。

通道插头（server.py）：
- OpenAI 兼容（QClaw / OpenClaw 自定义 API 直接填这个地址）
- OneBot v11 HTTP 回调（NapCat / QQ 小号）
- （飞书/QQ官方 ws 适配器后续按同接口接入）
"""

from __future__ import annotations

import datetime
import random as _random

from .v3.generate import generate_person, age_on
from .v4.memory import build_memories, build_beliefs
from .v4.person import Person
from .v4 import dialogue, timeline
from .v4.facts import facts_from_dict
from .v4.relations import build_relations
from .v4.persist import save_person, load_person, save_life, load_life
from .v4.extract import remember_from_input


class Session:
    """通道无关的"她"（单用户会话；一个种子=她一人）。

    mode：运行标签（verify=验证期 / production=正式期）。
    policy（仅 mode=production 时有效）：
      - warn（默认）：验证期数据**继续运行**，只提醒可转档（不强制——转档永远显式）；
      - strict：严格防污染——验证期数据拒绝加载（请先 promote 或 --clear）。
    """

    def __init__(self, seed: int, mode: str = "verify", policy: str = "warn") -> None:
        self.seed = seed
        self.mode = mode
        self.policy = policy
        # ── 相遇定格：她的人生在"相遇那天"生成完毕；此后由日子引擎推进 ──
        life = load_life(seed, allow_verify=True)
        meeting_str = (life.get("life") or {}).get("meeting_date") or ""
        meeting_date = (datetime.date.fromisoformat(meeting_str)
                        if meeting_str else datetime.date.today())
        self.result = generate_person(seed, now=meeting_date)
        self.birth_date = self.result["birth_date"]
        self.meeting_date = meeting_date

        she = Person(
            name="陈默识", seed=seed,
            birth_date=self.birth_date,
            age=age_on(self.birth_date, datetime.date.today()),
            memories=build_memories(self.result, facts=self.result["facts"]),
            beliefs=build_beliefs(self.result),
            facts=self.result["facts"],
            state=self.result["steps"][-1].state,
            meeting_date=meeting_date.isoformat(),
            meeting_age=self.result["current_age"],
        )
        she.build_flaws()
        she.relations = build_relations(self.result["facts"], she.memories,
                                        rng=_random.Random(f"{seed}:rel"))

        # 恢复持久化（她跨会话/跨渠道延续）
        loaded = load_person(she, seed, allow_verify=True)
        self.history: list[dict] = loaded.get("history") or []
        if loaded.get("warning"):
            print(f"[runtime] {loaded['warning']}")
        self.warning = loaded.get("warning")

        # ── 标签策略（不强制转档：标签随数据出身走；转档唯一入口 = promote 命令）──
        data_mode = (life.get("mode") if life.get("found")
                     else (loaded.get("mode") if loaded.get("found") else None))
        if data_mode is None:
            data_mode = mode                      # 新她：按运行标签落盘
        if mode == "production" and data_mode == "verify":
            if policy == "strict":
                raise RuntimeError(
                    "正式期（严格策略）检测到验证期数据（mode=verify）。\n"
                    "  ① 要延续这段关系：python -m moshi.promote --seed N（显式转档，一次性原子）\n"
                    "  ② 不要这段关系：python -m moshi.clear_data（清档重来）")
            print("[runtime] ⚠️ 正式期运行验证期数据：不强制转档，可继续使用；"
                  "如需正式期标签，执行 python -m moshi.promote --seed "
                  f"{seed}（显式、一次性、原子；她的一切都会延续）")
        self.mode = data_mode                     # 数据标签 = 她自己的出身（verify 保持 verify）
        self.warning = self.warning or (data_mode == "verify" and mode == "production" and
                                        "验证期数据（未转档，已继续运行）" or None)

        self.world_state = self.result["world"]
        if life.get("found"):
            lifed = life.get("life") or {}
            if lifed.get("facts"):
                she.facts = facts_from_dict(lifed["facts"])
            she.life_mood = lifed.get("life_mood", "")
            she.life_recent = lifed.get("life_recent", "")
            she.life_log = list(lifed.get("recent_days") or [])
            she.life_advanced_total = int(lifed.get("advanced_total", 0) or 0)
            she.structure_log = list(lifed.get("structure") or [])
            if life.get("world") is not None:
                self.world_state = life["world"]
            if life.get("relations"):
                she.relations = life["relations"]
        self.she = she
        self.last_life_day = int((life.get("life") or {}).get("last_life_day",
                                                              timeline.life_day_of(self.birth_date)))

        # ── 相遇背景（网友：从她的人生里长出来的"你们怎么认识的"；她记得，不是陌生人）──
        from .v4.meeting import generate_meeting_story
        lifed = life.get("life") or {}
        self.she.meeting_story = lifed.get("meeting_story") or {}
        if not self.she.meeting_story and self.she.facts is not None:
            self.she.meeting_story = generate_meeting_story(seed, self.she.facts)
        if self.she.meeting_story:
            self.she.trust = max(self.she.trust, 0.50)   # 信任基准：认识一段时间了（不是陌生人）

        # 离线补日子（她不在对话里时也在过日子）
        self._advance_if_needed()

    # ── 离线/跨日补日子（她一直在过日子；日子会传染今天的心情）──
    def _advance_if_needed(self) -> dict:
        today_day = timeline.life_day_of(self.birth_date)
        if today_day <= self.last_life_day:
            return {"advanced": 0, "structure": []}
        meta = timeline.advance_days(self.she, self.world_state, self.she.relations,
                                     self.birth_date, self.last_life_day, today_day, self.seed)
        if meta.get("relations") and meta["relations"] is not self.she.relations:
            self.she.relations = meta["relations"]
        if meta["advanced"] > 0:
            self.she.apply_absence(meta["advanced"])   # 缺席→依恋（她未必更想你，可能在淡）
        self.last_life_day = today_day
        return meta

    # ── 收到一句 → 她作答（完整管线：边界规则 + LLM 口吻 + 状态演化 + 持久化）──
    def on_message(self, text: str, image_url: str | None = None) -> dict:
        text = (text or "").strip()
        if not text and not image_url:
            return {"reply": "", "remembered": None, "touch": None}
        if image_url and not text:
            text = "（给你看一张照片）"
        meta = self._advance_if_needed()
        reply = dialogue.generate_reply(self.she, text, history=self.history,
                                        image_url=image_url)
        dialogue.apply_conversation_effects(self.she, dialogue.classify(text),
                                            len(reply), text)
        remembered = remember_from_input(self.she, text)
        if image_url:
            try:
                self.she.record_chronicle("special", "你给她看过一张照片（她看了）")
            except Exception:
                pass
        touch = dialogue.maybe_touch_on_you(self.she)
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": reply})
        self.save()
        return {"reply": reply, "remembered": remembered, "touch": touch,
                "offline_days": meta["advanced"],
                "offline_structure": [e["kind"] for e in meta["structure"]]}

    # ── tick：她会突然想起你（需通道支持主动推送；概率/条件见 maybe_touch_on_you）──
    def tick(self) -> str | None:
        self._advance_if_needed()
        try:
            return dialogue.maybe_touch_on_you(self.she)
        except Exception:
            return None

    def save(self) -> None:
        save_person(self.she, self.history, self.seed, mode=self.mode)
        save_life(self.she, self.world_state, self.she.relations, self.seed, mode=self.mode)
        self.last_life_day = timeline.life_day_of(self.birth_date)
