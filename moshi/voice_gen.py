"""话池生成器（voice_gen）—— 用锁定的 v2 参数（声线/种子）生成新的"她主动说的话"。

用法（在 .venv-cosy 下运行）：
  python -m moshi.voice_gen "嗯……今天忙完了没有？"
  python -m moshi.voice_gen "……你要是忙，就不用回。我就想说这句话。" --name pool_s6
产出：data/voice_cache/<name>_s<seed>.mp3（+wav + silk02header）
参数（与 pool_s1_s102 一致）：参考=prompt3.wav · INSTRUCT=v2 原文案 · speed=0.78 · seed 默认 102
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "tmp_cosy"))
sys.path.insert(0, str(_ROOT / "tmp_cosy" / "third_party" / "Matcha-TTS"))

import torch
import torchaudio
from cosyvoice.cli.cosyvoice import CosyVoice3

MODEL_DIR = _ROOT / "tmp_cosy" / "pretrained_models" / "CosyVoice3-0.5B"
PROMPT3 = _ROOT / "data" / "voice_cache" / "prompt3.wav"
OUT_DIR = _ROOT / "data" / "voice_cache"

INSTRUCT = ("You are a helpful assistant. 用很自然的语气说，语速放慢（像夜里慢慢跟朋友说话），"
            "声音里带一点点温度和倦意；问句像真的关心，叙述像真的说过的话，"
            "句子之间留自然的停顿，句尾轻轻落下来，绝不念读，绝不使劲。<|endofprompt|>")


def generate(text: str, seed: int = 102, name: str = "", speed: float = 0.78) -> Path:
    name = name or f"pool_t{int(time.time())}"
    cv = CosyVoice3(str(MODEL_DIR), load_trt=False, load_vllm=False, fp16=False)
    torch.manual_seed(seed)
    t0 = time.time()
    outs = list(cv.inference_instruct2(text, INSTRUCT, str(PROMPT3), stream=False, speed=speed))
    audio = torch.cat([o["tts_speech"] for o in outs], dim=1)
    wav = OUT_DIR / f"{name}_s{seed}.wav"
    torchaudio.save(str(wav), audio, cv.sample_rate)
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-i", str(wav), "-ar", "24000",
                    str(wav.with_suffix(".mp3"))], capture_output=True)
    from moshi import voice as _v
    silk = _v.mp3_to_silk_variant(wav.with_suffix(".mp3"), "02header")
    print(f"生成 {round(time.time() - t0, 1)}s（speed={speed}）→ {wav.with_suffix('.mp3').name}（silk: {silk.name}）")
    return wav.with_suffix(".mp3")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--seed", type=int, default=102)
    ap.add_argument("--name", default="")
    ap.add_argument("--speed", type=float, default=0.82)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    generate(a.text, seed=a.seed, name=a.name, speed=a.speed)
