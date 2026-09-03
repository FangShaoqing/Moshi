"""V4 持久化（persist）—— 让"她"跨会话延续（数据与种子绑定，验证期可删档）。

设计（协作方确认）：
- 数据与种子绑定：`data/SHE_<seed>/`（state.json + history.json + world.json + life.json）；
- **同一种子续接**：退出保存、启动加载（她记得上次、从你们的关系继续）；
- **换种子/显式删档才清**（同种子不丢）；
- **验证期隔离**：数据带 `"mode": "verify"`（正式版启动检测到 verify 数据 → 拒绝/提示清理，
  从机制上防"验证期数据污染正式期"；正式版切换为 `"mode": "production"`）。

存储内容（她"活着"的状态）：
- 关系阶段（interaction_count / deep_talks / special_moments）
- 信任 / 情绪状态（state）
- 她记住你的事（shared_memories）
- 你们的对话历史（history）
- ④ 相遇后的日子：world.json（世界运势 + 她世界里的人）+ life.json（日子日志/基调）
  —— **一个种子 = 一个宇宙 = 一份全部状态**；全部文件都在该种子目录下，绝不跨种子共享。
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from .person import Person
from ..v3.world import WorldState
from .relations import Relation
from .timeline import life_day_of
from .facts import facts_to_dict, facts_from_dict

# 数据根目录（项目根下 data/）
DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


def _seed_dir(seed: int) -> Path:
    return DATA_ROOT / f"SHE_{seed}"


def save_person(person: Person, history: list[dict], seed: int, mode: str = "verify") -> Path:
    """把"她 + 对话历史"保存到 data/SHE_<seed>/。返回保存路径。"""
    d = _seed_dir(seed)
    d.mkdir(parents=True, exist_ok=True)
    state = {
        "mode": mode,                      # 隔离标识：verify（验证期）/ production（正式）
        "seed": seed,
        "name": person.name,
        "trust": person.trust,
        "state": person.state.as_list() if person.state else None,
        "interaction_count": person.interaction_count,
        "deep_talks": person.deep_talks,
        "special_moments": person.special_moments,
        "shared_memories": person.shared_memories,
        # ③ 被改变 + 缺点 + 情绪（跨会话延续）
        "toward_you": person.toward_you,
        "affected_beliefs": person.affected_beliefs,
        "flaws": person.flaws,
        "is_angry": getattr(person, "is_angry", False),
        "exhausted": getattr(person, "exhausted", False),
        "angry_turns": getattr(person, "angry_turns", 0),
        # 依恋（跨会话延续）
        "security": person.security,
        "dependence": person.dependence,
        # ① 你们的故事（重要时刻沉淀——长期陪伴的厚度）
        "chronicle": getattr(person, "chronicle", []),
        "chronicle_old": getattr(person, "chronicle_old", ""),
    }
    (d / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "history.json").write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def load_person(person: Person, seed: int, *, allow_verify: bool = True) -> dict:
    """从 data/SHE_<seed>/ 加载"她 + 历史"。返回 {"found": bool, "mode": str, "history": [...]}。

    mode 隔离：
    - 若数据 mode == "production" → 正常加载（正式）；
    - 若 mode == "verify" 且 调用方 allow_verify=True（验证期）→ 正常加载；
    - 若 mode == "verify" 且 调用方 allow_verify=False（正式版）→ 拒绝（返回 found=False + warning）。
    """
    d = _seed_dir(seed)
    state_f = d / "state.json"
    hist_f = d / "history.json"
    result = {"found": False, "mode": None, "history": [], "warning": None}
    if not state_f.exists():
        return result
    try:
        state = json.loads(state_f.read_text(encoding="utf-8"))
    except Exception:
        return result
    mode = state.get("mode", "verify")
    result["mode"] = mode
    if mode == "verify" and not allow_verify:
        result["warning"] = "检测到验证期数据（mode=verify）。正式版拒绝加载——请先清档（moshi.clear_data）。"
        return result
    if state.get("seed") != seed:
        result["warning"] = "数据种子与当前种子不符，拒绝加载。"
        return result
    # 恢复她
    try:
        from ..v2.state import StateVector
        person.trust = state.get("trust", 0.35)
        if state.get("state"):
            person.state = StateVector(*state["state"])
        person.interaction_count = state.get("interaction_count", 0)
        person.deep_talks = state.get("deep_talks", 0)
        person.special_moments = state.get("special_moments", [])
        person.shared_memories = state.get("shared_memories", [])
        # ③ 被改变 + 缺点 + 情绪（跨会话延续）
        person.toward_you = state.get("toward_you", {})
        person.affected_beliefs = state.get("affected_beliefs", [])
        person.flaws = state.get("flaws", [])
        person.is_angry = state.get("is_angry", False)
        person.exhausted = state.get("exhausted", False)
        person.angry_turns = state.get("angry_turns", 0)
        person.security = state.get("security", 0.5)
        person.dependence = state.get("dependence", 0.3)
        person.chronicle = state.get("chronicle", [])
        person.chronicle_old = state.get("chronicle_old", "")
        person.seed = seed
    except Exception:
        return result
    if hist_f.exists():
        try:
            result["history"] = json.loads(hist_f.read_text(encoding="utf-8"))
        except Exception:
            result["history"] = []
    result["found"] = True
    return result


def save_life(person: Person, world: WorldState | None, relations: list[Relation] | None,
              seed: int, mode: str = "verify") -> Path:
    """保存"她相遇后的日子"（世界运势 + 她世界里的人 + 日子日志）到 data/SHE_<seed>/。

    - world.json：世界响应快照 + 配角状态（她在你不在时继续过日子/关系微动）；
    - life.json：人生第几天（last_life_day）、最近日子日志、生活基调（life_mood）。
    全部属于该种子；`.clear_all_data()` 一次性清空。
    """
    d = _seed_dir(seed)
    d.mkdir(parents=True, exist_ok=True)

    world_data: dict[str, Any] = {
        "mode": mode,
        "seed": seed,
        "responses": dict(getattr(world, "responses", {}) or {}),
        "relations": [],
    }
    for rel in relations or []:
        world_data["relations"].append({
            "name": rel.name, "kind": rel.kind, "base_fact": rel.base_fact,
            "mood": rel.mood, "recent_thing": rel.recent_thing,
            "bonds_with_her": rel.bonds_with_her,
            "proximity": float(rel.proximity), "tendency": rel.tendency,
        })
    (d / "world.json").write_text(
        json.dumps(world_data, ensure_ascii=False, indent=2), encoding="utf-8")

    birth = person.birth_date
    life_data: dict[str, Any] = {
        "mode": mode,
        "seed": seed,
        "last_life_day": life_day_of(birth) if birth is not None else 0,
        "life_mood": getattr(person, "life_mood", ""),
        "life_recent": getattr(person, "life_recent", ""),
        "recent_days": list(getattr(person, "life_log", []) or [])[-7:],
        "advanced_total": int(getattr(person, "life_advanced_total", 0) or 0),
        # ── 结构层（人生不许编：事实=真相，快照持久化；大事记录在案）──
        "facts": facts_to_dict(person.facts) if person.facts is not None else None,
        "structure": list(getattr(person, "structure_log", []) or []),
        "meeting_date": getattr(person, "meeting_date", "") or "",
        "meeting_age": int(getattr(person, "meeting_age", 0) or 0),
        # ── 相遇背景（你们怎么认识的——她记得；持久化，不再重新生成）──
        "meeting_story": dict(getattr(person, "meeting_story", {}) or {}),
    }
    (d / "life.json").write_text(
        json.dumps(life_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def load_life(seed: int, *, allow_verify: bool = True) -> dict:
    """从 data/SHE_<seed>/ 加载"她相遇后的日子"。返回：
    {"found", "mode", "warning", "world": WorldState|None, "relations": [Relation]|None, "life": dict|None}

    mode 隔离（与 state.json 同规则）：
    - 数据 mode=="verify" 且 调用方 allow_verify=False（正式版）→ 拒绝（found=False + warning）。
    """
    result: dict[str, Any] = {"found": False, "mode": None, "warning": None,
                              "world": None, "relations": None, "life": None}
    d = _seed_dir(seed)
    wf, lf = d / "world.json", d / "life.json"
    if not wf.exists():
        return result
    try:
        wdata = json.loads(wf.read_text(encoding="utf-8"))
    except Exception:
        return result
    mode = wdata.get("mode", "verify")
    result["mode"] = mode
    if mode == "verify" and not allow_verify:
        result["warning"] = "检测到验证期日子数据（mode=verify）。正式版拒绝加载——请先清档（moshi.clear_data）。"
        return result
    if wdata.get("seed") != seed:
        result["warning"] = "日子数据种子与当前种子不符，拒绝加载。"
        return result
    try:
        if isinstance(wdata.get("responses"), dict):
            result["world"] = WorldState(
                responses={k: float(v) for k, v in wdata["responses"].items()})
        rels = []
        for row in wdata.get("relations", []) or []:
            rels.append(Relation(
                name=row.get("name", ""), kind=row.get("kind", ""),
                base_fact=row.get("base_fact", ""),
                mood=row.get("mood", "还行"), recent_thing=row.get("recent_thing", ""),
                bonds_with_her=row.get("bonds_with_her", ""),
                proximity=float(row.get("proximity", 0.5)),
                tendency=row.get("tendency", "plain")))
        result["relations"] = rels if rels else None
    except Exception:
        return result
    if lf.exists():
        try:
            result["life"] = json.loads(lf.read_text(encoding="utf-8"))
        except Exception:
            result["life"] = None
    result["found"] = True
    return result


def clear_all_data() -> int:
    """验证期一键删档：清空 data/ 下所有 SHE_<seed>/ 目录。返回清除的目录数。"""
    if not DATA_ROOT.exists():
        return 0
    removed = 0
    for child in DATA_ROOT.iterdir():
        if child.is_dir() and child.name.startswith("SHE_"):
            import shutil
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return removed


def data_root_exists() -> bool:
    return DATA_ROOT.exists()
