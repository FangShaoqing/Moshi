"""转档（promote）—— 把"她的数据"从验证期标签改成正式期标签（显式、一次性、原子）。

设计（协作方 2026-09-01）：
- **只改标签**（mode: verify → production），不触碰她的人格/记忆/信任/故事/日子——她不变；
- **不强制**：唯一入口是显式执行本命令；正式期**不会**拒绝验证期数据
  （默认 warn：提醒但不拦；想要严格防污染用 `--mode-policy strict`，那是它的职责）；
- **原子**：每个文件临时写入 + `os.replace`（不会写出半个文件）。

用法：
  python -m moshi.promote --status          # 看看各种子当前标签（verify / production / 无数据）
  python -m moshi.promote --seed 12345678   # 指定种子转档
  python -m moshi.promote --all             # 全部转档
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .v4.persist import DATA_ROOT

_MODE_FILES = ("state.json", "world.json", "life.json")
_VERIFY = "verify"
_PRODUCTION = "production"


def _seed_dir(seed: int) -> Path:
    return DATA_ROOT / f"SHE_{seed}"


def _read_mode(path: Path) -> str | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("mode")
    except Exception:
        return None


def seed_status(seed: int) -> str:
    """该种子的标签：production / verify / none（无数据）。"""
    d = _seed_dir(seed)
    if not d.exists():
        return "none"
    modes = [_read_mode(d / f) for f in _MODE_FILES]
    modes = [m for m in modes if m]
    if not modes:
        return "none"
    return _PRODUCTION if all(m == _PRODUCTION for m in modes) else _VERIFY


def promote_seed(seed: int) -> dict:
    """单种子转档：verify → production（原子；已是 production / 无数据则不动）。"""
    d = _seed_dir(seed)
    changed: list[str] = []
    if not d.exists():
        return {"seed": seed, "changed": changed, "mode": "none"}
    for f in _MODE_FILES:
        path = d / f
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("mode") != _VERIFY:
            continue
        data["mode"] = _PRODUCTION
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)                     # 原子替换
        changed.append(f)
    return {"seed": seed, "changed": changed,
            "mode": _PRODUCTION if changed else seed_status(seed)}


def promote_all() -> list[dict]:
    """全部种子转档（有数据的所有 SHE_* 目录）。"""
    out = []
    if DATA_ROOT.exists():
        for child in sorted(DATA_ROOT.iterdir()):
            if child.is_dir() and child.name.startswith("SHE_"):
                try:
                    out.append(promote_seed(int(child.name[4:])))
                except ValueError:
                    continue
    return out


def show_status(seeds: list[int] | None = None) -> None:
    """打印各种子标签（--status / 默认输出）。"""
    entries = []
    if seeds:
        entries = [(s, seed_status(s)) for s in seeds]
    elif DATA_ROOT.exists():
        for child in sorted(DATA_ROOT.iterdir()):
            if child.is_dir() and child.name.startswith("SHE_"):
                try:
                    s = int(child.name[4:])
                except ValueError:
                    continue
                entries.append((s, seed_status(s)))
    if not entries:
        print("（没有任何种子数据）")
        return
    print(f"{'种子':<12}{'标签':<12}")
    for s, m in entries:
        print(f"{s:<12}{m:<12}")


def main() -> None:
    ap = argparse.ArgumentParser(description="转档：验证期数据 → 正式期标签（显式、一次性、原子）")
    ap.add_argument("--seed", type=int, nargs="*", help="指定种子转档")
    ap.add_argument("--all", action="store_true", help="全部转档")
    ap.add_argument("--status", action="store_true", help="只看标签，不动数据")
    args = ap.parse_args()

    if args.status:
        show_status(args.seed)
        return
    if args.all:
        results = promote_all()
        for r in results:
            print(f"种子 {r['seed']}: {r['mode']}（文件 {r['changed'] or '无需改动'}）")
        print(f"完成：处理 {len(results)} 个种子数据目录。")
        return
    if not args.seed:
        show_status()
        print("\n提示：转档要指定种子（--seed N）或 --all。")
        return
    for s in args.seed:
        r = promote_seed(s)
        print(f"种子 {s}: {r['mode']}（文件 {r['changed'] or '无需改动'}）")


if __name__ == "__main__":
    main()
