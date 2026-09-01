"""数据清理命令 —— 验证期一键删档。

用法：  python -m moshi.clear_data
（清空 data/ 下所有 SHE_<seed>/ 目录：验证期测完即清，保证不污染正式阶段。）
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .v4.persist import clear_all_data


def main() -> None:
    n = clear_all_data()
    print(f"已清空 {n} 个种子数据目录。" if n else "没有残留的种子数据。")


if __name__ == "__main__":
    main()
