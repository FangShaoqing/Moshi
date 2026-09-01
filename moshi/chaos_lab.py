"""Chaos Lab · 独立混沌内核演示 —— 敏感依赖的可验证证据。

在把"混沌"接进 V3 引擎之前，先用最经典的混沌映射证明：
- "微扰被指数放大"是**真的、可复现的**（而非我们脑补）；
- 敏感依赖的机制：**拉伸（x(1-x) 的非线性）**，而 V3 之前的失败是因为**只有收缩**。

运行：  python -m moshi.chaos_lab
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def logistic(x: float, r: float) -> float:
    """最经典的一维混沌映射：x' = r·x·(1-x)。"""
    return r * x * (1.0 - x)


def run_logistic(x0: float, r: float, steps: int) -> list[float]:
    xs = [x0]
    for _ in range(steps):
        xs.append(logistic(xs[-1], r))
    return xs


def divergence(seq_a: list[float], seq_b: list[float]) -> list[float]:
    return [abs(a - b) for a, b in zip(seq_a, seq_b)]


def demo(r: float, eps: float, steps: int, label: str) -> None:
    print(f"\n───── {label}：x' = r·x·(1-x)，r={r}，微扰 ε={eps}，迭代 {steps} 步 ─────")
    xa = 0.4
    xb = 0.4 + eps
    seq_a = run_logistic(xa, r, steps)
    seq_b = run_logistic(xb, r, steps)
    print(f"{'步':>3} {'A':>10} {'B':>10} {'差值':>12}")
    for i in range(steps + 1):
        d = abs(seq_a[i] - seq_b[i])
        print(f"{i:>3} {seq_a[i]:>10.7f} {seq_b[i]:>10.7f} {d:>12.3e}")
    final = abs(seq_a[-1] - seq_b[-1])
    ratio = final / eps if eps else float("inf")
    magnified = final > eps * 10
    print(f"→ 最终差值 {final:.3e}；初始微扰 {eps:.1e}；放大比 {ratio:.1f}x "
          f"{'★ 敏感依赖成立（微扰被放大）' if magnified else '（微扰未被放大）'}")


def demo_stable(r: float, eps: float, steps: int) -> None:
    """对照组：低 r（稳定区）→ 微扰衰减，作为"非混沌"的对照。"""
    print(f"\n───── 对照组（稳定区，非混沌）r={r} ─────")
    xa = 0.4
    xb = 0.4 + eps
    seq_a = run_logistic(xa, r, steps)
    seq_b = run_logistic(xb, r, steps)
    for i in (0, steps // 2, steps):
        print(f"  第{i:>3}步：差值 = {abs(seq_a[i] - seq_b[i]):.3e}")
    final = abs(seq_a[-1] - seq_b[-1])
    print(f"→ 最终差值 {final:.3e}（对比混沌区：微扰被衰减而不是放大）")


def main() -> None:
    print("=" * 66)
    print("  Chaos Lab · 敏感依赖的可验证证据 —— V3 之前是[收缩]，这里演示[拉伸]")
    print("=" * 66)

    # 混沌区：r=3.99（Logistic 映射在 r>3.5699... 进入混沌）
    demo(r=3.99, eps=1e-9, steps=40, label="混沌区")
    # 稳定区：r=3.2（收敛到不动点，微扰衰减）
    demo_stable(r=3.2, eps=1e-9, steps=40)

    print("\n" + "=" * 66)
    print("  结论解读")
    print("=" * 66)
    print("  · 混沌区（r=3.99）：微扰 1e-9 经 ~30 步后差值达 O(0.1) —— 被指数放大。")
    print("    原因：x(1-x) 的非线性是[拉伸]机制，且多次迭代把微扰反复放大。")
    print("  · 稳定区（r=3.2）：微扰被衰减 —— 系统收敛，没有拉伸。")
    print("  → V3 之前失败根因：只有[α回归+tanh饱和+clamp]这些[收缩]机制，缺[拉伸]机制。")


if __name__ == "__main__":
    main()
