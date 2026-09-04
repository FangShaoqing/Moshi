"""sambert 音色试听（audition）—— 用百炼免费额度批量生成候选女声，你听选"她的音色"。

用法（venv）：
  python -m moshi.sambert_audition                 # 全部候选生成（免费额度，每句几毫元）
  python -m moshi.sambert_audition --voice zhide   # 只生成一个
产出：data/voice_cache/sambert_<voice>.mp3（同一句"嗯……今天忙完了没有？"便于横向比）
选定后：把音色名告诉我 → 我用它生成"情绪参考音频"→ 喂本地 CosyVoice 克隆。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_OUT = _ROOT / "data" / "voice_cache"
_KEY_FILE = _ROOT / "config" / "secrets.json"

# 中文候选（性别以听为准——文档只给名字；按气质先试这些）
CANDIDATES = ["zhixia", "zhide", "zhifei", "zhiyue", "zhijia", "zhichu", "zhigui", "zhistella"]
SAMPLE = "嗯……今天忙完了没有？"


def key() -> str:
    import os
    env = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if env:
        return env
    try:
        v = (json.loads(_KEY_FILE.read_text(encoding="utf-8")).get("DASHSCOPE_API_KEY") or "").strip()
        if v and not v.startswith("在此"):
            return v
    except Exception:
        pass
    return ""


def synth(voice: str, text: str = SAMPLE) -> Path:
    import dashscope
    dashscope.api_key = key()
    r = dashscope.SpeechSynthesizer.call(model=f"sambert-{voice}-v1", text=text,
                                         format="mp3", sample_rate=48000)
    resp = r.get_response() or {}
    if resp.get("status_code") != 200:
        raise RuntimeError(f"{voice}: {resp.get('status_code')} {str(resp.get('message'))[:120]}")
    data = r.get_audio_data()
    if not data:
        raise RuntimeError(f"{voice}: 返回无音频")
    _OUT.mkdir(parents=True, exist_ok=True)
    out = _OUT / f"sambert_{voice}.mp3"
    out.write_bytes(data)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not key():
        print("[audition] 缺少 DASHSCOPE_API_KEY——config/secrets.json 填入后重试")
        return
    voices = [args.voice] if args.voice else CANDIDATES
    for v in voices:
        try:
            t0 = time.time()
            out = synth(v)
            print(f"✅ {v}  → {out.name}（{round(time.time() - t0, 1)}s）")
        except Exception as e:
            print(f"❌ {v}  {e}")


if __name__ == "__main__":
    main()
