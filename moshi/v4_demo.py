"""V4 · 相遇演示 —— 命令行对话：你遇到 "当下的陈默识"（含持久化：她跨会话延续）。

运行：
  python -m moshi.v4_demo                 # 默认种子，续接上次（若有数据）
  python -m moshi.v4_demo --clear         # 先清档（验证期一键删档，再启动全新）
  python -m moshi.v4_demo 12345678        # 指定种子
  python -m moshi.v4_demo 12345678 --clear

LLM：默认读取 config/secrets.json 的 DEEPSEEK_API_KEY；未配置自动降级规则模板。
持久化：data/SHE_<seed>/（同种子续接；换种子/--clear 才清；mode=verify 隔离）。
④ 相遇后的日子：你不在这段时间，她照常过日子（world.json/life.json 同种子目录下）。
   她的人生在"相遇那天"定格生成（认识她之前，她的人生已书写完毕）；
   相遇后由日子引擎推进（日常 + 人生大事：毕业/搬家/换工作 → 事实层同步更新）。
"""

from __future__ import annotations

import datetime
import random as _random
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .v3.generate import generate_person, age_on
from .v4.memory import build_memories, build_beliefs
from .v4.person import Person
from .v4 import dialogue, timeline
from .v4.llm import llm_available
from .v4.persist import save_person, load_person, save_life, load_life, clear_all_data


def main() -> None:
    args = sys.argv[1:]
    clear_first = "--clear" in args
    nums = [a for a in args if a.isdigit()]
    seed = int(nums[0]) if nums else 20260827

    if clear_first:
        n = clear_all_data()
        print(f"[已清档] 清除 {n} 个种子数据目录。")

    # ── ④ 相遇定格：先查"这段关系"的存在（决定她的人生在哪天定格）──
    life = load_life(seed)
    meeting_str = (life.get("life") or {}).get("meeting_date") or ""
    meeting_date = (datetime.date.fromisoformat(meeting_str)
                    if meeting_str else datetime.date.today())

    # 她的人生在"相遇那天"定格生成（认识她之前她的人生已书写完毕；此后由日子引擎推进）
    result = generate_person(seed, now=meeting_date)
    today_age = age_on(result["birth_date"], datetime.date.today())   # 她现在几岁（现实时间流逝）

    she = Person(
        name="陈默识",
        seed=seed,
        birth_date=result["birth_date"],
        age=today_age,
        memories=build_memories(result, facts=result["facts"]),
        beliefs=build_beliefs(result),
        facts=result["facts"],
        state=result["steps"][-1].state,
        meeting_date=meeting_date.isoformat(),
        meeting_age=result["current_age"],
    )
    she.build_flaws()   # 缺点（她真实的毛病）
    # 关系网（她世界里的人——轻量生活引擎；种子化：同种子=同一个她=同一批人）
    from .v4.relations import build_relations
    she.relations = build_relations(result["facts"], she.memories,
                                     rng=_random.Random(f"{seed}:rel"))

    # ── 持久化：启动加载（同种子续接）──
    loaded = load_person(she, seed)
    history: list[dict] = loaded.get("history") or []
    if loaded.get("warning"):
        print(f"[警告] {loaded['warning']}")

    # ── ④ 相遇后的日子：她"遇到你之后"还在过日子 ──
    #    一个种子 = 一个宇宙 = 一份全部状态（world.json/life.json 都在该种子目录下）
    world_state = result["world"]
    if life.get("found"):
        lifed = life.get("life") or {}
        # 结构层：事实=快照（人生不许编——相遇后事实不再随年龄漂移，只随"大事"真的改变）
        if lifed.get("facts"):
            from .v4.facts import facts_from_dict
            she.facts = facts_from_dict(lifed["facts"])
        she.life_mood = lifed.get("life_mood", "")
        she.life_recent = lifed.get("life_recent", "")
        she.life_log = list(lifed.get("recent_days") or [])
        she.life_advanced_total = int(lifed.get("advanced_total", 0) or 0)
        she.structure_log = list(lifed.get("structure") or [])
        if life.get("world") is not None:
            world_state = life["world"]
        if life.get("relations"):
            she.relations = life["relations"]
        # 离线期间她过了多少天：补上她的日子（确定性：同种子+同时间线→同样的日子）
        today_day = timeline.life_day_of(result["birth_date"])
        last_day = int(lifed.get("last_life_day", today_day))
        if today_day > last_day:
            meta = timeline.advance_days(she, world_state, she.relations,
                                         result["birth_date"], last_day, today_day, seed)
            if meta.get("relations") and meta["relations"] is not she.relations:
                she.relations = meta["relations"]      # 结构事件更新了配角（毕业/搬家/换工作）
            if meta["advanced"] > 0:
                # ② 缺席→依恋：你离开的日子真实影响她（依赖淡/焦虑型更不安——不是设定她等你）
                she.apply_absence(meta["advanced"])
                print(f"〔{meta['advanced']} 天没见。她照常过着日子：{she.life_recent}〕")
            for ev in meta["structure"]:
                label = {"graduation": "她毕业了", "move": "她搬了家",
                         "job_change": "她换了工作"}.get(ev.get("kind"), "她身上发生了事")
                print(f"〔大事：{label}〕")

    if loaded.get("found"):
        stage = she.relationship_stage()
        print(f"〔续接：她记得你们之前的事（关系：{stage}）〕")
    else:
        print(f"〔新的她〕")

    print("=" * 66)
    print(f"  你遇到了一位 {she.age} 岁的女性，叫陈默识。（seed={seed}）")
    print("  你对她一无所知。试着和她聊聊天吧——她的过去，只能靠相处慢慢知道。")
    print("  输入 'quit' 结束（会保存你们的进展，下次续接）。")
    print("=" * 66)
    print("\n[LLM] " + ("已配置 DeepSeek" if llm_available() else "未配置 API Key —— 降级为规则模板"))

    # ② 日子→状态：她的生活状态（世界近况）喂进当前心情（她是一个持续活着的人）
    try:
        she.sync_from_life()
    except Exception:
        pass

    while True:
        try:
            user_input = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n（离开了）")
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "退出"):
            print(f"{she.name}：嗯，下次再说吧。")
            break

        reply = dialogue.generate_reply(she, user_input, history=history)
        dialogue.apply_conversation_effects(she, dialogue.classify(user_input),
                                            len(reply), user_input)
        from .v4.extract import remember_from_input
        remembered = remember_from_input(she, user_input)
        print(f"{she.name}> {reply}")
        if remembered:
            print(f"  〔她记住了：{user_input[:30]}{'…' if len(user_input) > 30 else ''}〕")

        touch = dialogue.maybe_touch_on_you(she)
        if touch:
            print(f"{she.name}>（突然）{touch}")

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": reply})

    # ── 退出：保存（同种子续接）──
    save_person(she, history, seed)
    save_life(she, world_state, she.relations, seed)
    print(f"〔已保存。下次运行同样的 seed，她会记得这次；离开的这几天，她也会照常过日子。〕")


if __name__ == "__main__":
    main()
