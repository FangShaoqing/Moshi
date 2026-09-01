"""V1 · 演示 —— 确定性混沌 + 先在条件生发 + 人格涌现。

目的：验证"系统自己孕育一个人"，而不是手写。重点看两件事：
  (1) 同种子 → 完全同一个人（可复现）；
  (2) 近种子 → 完全不同的人生（确定混沌的敏感依赖）。

运行：  python -m moshi.v1_demo
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .v1.generate import generate_person


def person_signature(moshi) -> str:
    """用一个可比较的签名（各认识的关键内容）来判定"两个人是否一样"。"""
    parts = [f"{b.domain}|{b.tendency}|{round(b.strength, 3)}" for b in moshi.beliefs]
    return "; ".join(parts) or "(无认识)"


def show_person(moshi, pre, tag: str) -> None:
    print(f"\n───── {tag} ─────")
    print(f"先在条件：{pre.describe()}")
    print(f"人格（{moshi.belief_count} 条认识）：")
    for b in moshi.beliefs:
        print(f"  · {b.as_condition()}")


def main() -> None:
    print("=" * 62)
    print("  Moshi V1 · 生命引擎 —— 系统自己孕育一个人")
    print("=" * 62)

    seed = 20260827
    moshi_a, pre_a, _ = generate_person(seed)
    moshi_b, pre_b, _ = generate_person(seed)

    print("\n【验证 1】同种子 → 是否完全同一个人？")
    sig_a = person_signature(moshi_a)
    sig_b = person_signature(moshi_b)
    print(f"  种子={seed} 生成两次，人格签名相等？ → {sig_a == sig_b}")
    if sig_a != sig_b:
        print("  !! 同种子却不同 → 破坏了确定性混沌（应可复现）")
        return
    show_person(moshi_a, pre_a, f"陈默识 · seed={seed}")

    print("\n\n【验证 2】近种子（seed 微扰 ±1）→ 是否长出不同人生？")
    sig_ref = sig_a
    for near in (seed + 1, seed - 1):
        moshi_n, pre_n, _ = generate_person(near)
        sig_n = person_signature(moshi_n)
        differs = (pre_n.birth_place != pre_a.birth_place
                   or pre_n.family_class != pre_a.family_class
                   or sig_n != sig_ref)
        print(f"  种子={near}：先在条件差异？{'有' if differs else '无'}"
              f"；人格签名不同？{'有' if sig_n != sig_ref else '无'}")
        print(f"    ↳ 生长出：{pre_n.describe()}")
        print(f"    ↳ 认识数={moshi_n.belief_count}，首条：{moshi_n.beliefs[0].describe() if moshi_n.beliefs else '(无)'}")


if __name__ == "__main__":
    main()
