"""voice_test —— 试听她的候选音色（MiMo VoiceDesign）。

用法：
  python -m moshi.voice_test                    # 三个候选都生成（A/B/C），打印 mp3/silk 路径
  python -m moshi.voice_test --candidate B      # 只生成 B
  python -m moshi.voice_test "嗯，我在。你最近怎么样？"   # 自定义试听文本

前提：config/secrets.json 已配 MIMO_API_KEY（没有则退回 Edge TTS 兜底——试的是兜底音色）。
试听后把满意的字母写进 moshi/voice.py 的 VOICE_DESIGN_DEFAULT。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import voice as V

SAMPLE = "嗯，我在。你最近怎么样？"


def main() -> None:
    ap = argparse.ArgumentParser(description="试听她的候选音色")
    ap.add_argument("--candidate", choices=tuple(V.VOICE_DESIGNS.keys()))
    ap.add_argument("text", nargs="?", default=SAMPLE, help="试听文本")
    args = ap.parse_args()

    src, key = V.mimo_key_source()
    if src == "无":
        print("[voice_test] 未配置 MIMO_API_KEY → 本次试听为 Edge TTS 兜底音色"
              "（想试 MiMo 专有声：config/secrets.json 填 MIMO_API_KEY）")
    elif src == "环境变量":
        print(f"[voice_test] ⚠️ 正在使用【环境变量】MIMO_API_KEY（长度 {len(key)}）——"
              "它不是配置文件的密钥；如因此 401，请删除环境变量：\n"
              "          在 PowerShell 里执行：Remove-Item Env:\\MIMO_API_KEY")
    else:
        print("[voice_test] 正在使用【配置文件】MIMO_API_KEY（config/secrets.json）")

    candidates = [args.candidate] if args.candidate else list(V.VOICE_DESIGNS)
    for c in candidates:
        try:
            if V.mimo_key():
                mp3 = V.synth_mimo(args.text, c)
            else:
                mp3 = V.synth_edge(args.text)            silk = V.mp3_to_silk(mp3)
            print(f"【{c}】{Path(mp3)}")
            print(f"     {Path(silk)}   <- 这个就是 QQ 语音（silk）")
            print(f"     设计：{V.VOICE_DESIGNS[c]}")
        except Exception as e:
            print(f"【{c}】失败：{e}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
