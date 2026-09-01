"""whoami —— 打印"她"是谁（形象/声音/事实；供生图与设置头像用）。

用法：python -m moshi.whoami [seed]    # 默认 20260827
说明：她的形象是种子派生的事实（一个种子=一张脸）；生图请用这里的描述保持一致性。
"""

from __future__ import annotations

import sys

from .v3.generate import generate_person
from . import voice as voice_mod


def main() -> None:
    nums = [a for a in sys.argv[1:] if a.isdigit()]
    seed = int(nums[0]) if nums else 20260827
    res = generate_person(seed)
    f = res["facts"]
    print(f"—— {res['current_age']} 岁的她 · seed={seed} ——")
    print()
    print("【形象】（长这样是事实——生图/描述照着来）")
    print(f"  身高：{f.height}")
    print(f"  头发：{f.hair}")
    print(f"  长相：{f.face}")
    print(f"  穿着：{f.style}")
    print("  气质关键词：普通、素净、安静、耐看；沉静内敛，话不多（不是精致 AI 脸）")
    print()
    print(f"【声音】{voice_mod.describe_voice()}")
    print()
    print("【她是谁】（简述）")
    print(f"  {f.current_city} · {f.education_current} · {f.job} · 喜欢{'、'.join(f.interests)}")
    print(f"  {f.keeps}")
    print()
    print("生图建议：写实风格 · 正脸/半身 · 日常光线 · 不化妆或淡妆 · 低于 30 岁中国女性 ·")
    print("         素净衣着（贴合上面穿着描述）· 禁止：网红脸、精修、AI 塑料感")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
