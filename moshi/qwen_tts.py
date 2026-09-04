"""Qwen-TTS 适配（qwen_tts）—— 音色设计 + 设计音色合成（百炼）。

- design_voice(voice_prompt) → voice_id（$0.2/音色；描述多维：性别/年龄/音调/语速/情感/特点）
- synth(text, voice_id) → mp3（model=qwen3-tts-vd-<date>；1元/百万字符、输出不计费）
用法（main 环境亦可——纯 urllib）：
  python -m moshi.qwen_tts --design   # 生成 2 个候选音色 + 各一句样句
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_OUT = _ROOT / "data" / "voice_cache"
_KEY_FILE = _ROOT / "config" / "secrets.json"
BASE = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
VD_MODEL = "qwen3-tts-vd-2026-01-26"


def workspace() -> str:
    import os as _os
    env = _os.environ.get("DASHSCOPE_WORKSPACE", "").strip()
    if env:
        return env
    try:
        v = (json.loads(_KEY_FILE.read_text(encoding="utf-8")).get("DASHSCOPE_WORKSPACE") or "").strip()
        if v:
            return v
    except Exception:
        pass
    return ""


def design_voice(voice_prompt: str, name: str = "moshi_voice") -> str:
    """文字 → 设计音色 voice_id（Qwen 设计：dashscope customization + action=create）。

    正确姿势（2026-09-04 实测，花了两轮冤枉钱才确认）：
      POST /api/v1/services/audio/tts/customization
      {"model": "qwen-voice-design",
       "input": {"action": "create", "target_model": VD_MODEL,
                 "preferred_name": name, "voice_prompt": …, "preview_text": …},
       "parameters": {"sample_rate": 24000, "response_format": "wav"}}
    （对比：CosyVoice 设计是 model=voice-enrollment + action=create_voice + prefix —— 别混）
    """
    payload = {"model": "qwen-voice-design",
               "input": {"action": "create", "target_model": VD_MODEL,
                         "preferred_name": name,
                         "voice_prompt": voice_prompt,
                         "preview_text": "嗯，今天忙完了没有？我这边下雨了，你那边呢？"},
               "parameters": {"sample_rate": 24000, "response_format": "wav"}}
    req = urllib.request.Request(
        "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key()}"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read().decode("utf-8"))
    out = d.get("output", {}) or {}
    vid = out.get("voice") or out.get("voice_id") or out.get("id")
    if vid:
        return vid
    raise RuntimeError(f"设计失败: {json.dumps(d, ensure_ascii=False)[:220]}")


def key() -> str:
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


def _post(payload: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        BASE, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key()}"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def synth_flash(text: str, voice: str = "Maia", instructions: str = "",
                language: str = "Chinese") -> Path:
    """内置音色合成（qwen3-tts-flash；instructions 非空自动升 instruct-flash → 情感指令）。

    Maia =「四月」（知性与温柔的碰撞·女性，百炼内置）。
    """
    import base64 as _b64
    model = "qwen3-tts-instruct-flash" if instructions else "qwen3-tts-flash"
    payload = {"model": model,
               "input": {"text": text, "voice": voice, "language_type": language}}
    if instructions:
        payload["input"]["instructions"] = instructions
    d = _post(payload, timeout=180)
    out = d.get("output", d) or {}
    a = out.get("audio")
    if isinstance(a, dict):
        audio = a.get("data") or a.get("url")
    else:
        audio = a or out.get("audio_url") or out.get("url")
    if isinstance(audio, str) and audio.startswith("http"):
        with urllib.request.urlopen(audio, timeout=120) as r:
            audio = "base64," + _b64.b64encode(r.read()).decode()
    if isinstance(audio, str) and audio.startswith("base64,"):
        audio = audio[7:]
    if not audio:
        raise RuntimeError(f"合成无音频: {json.dumps(d, ensure_ascii=False)[:200]}")
    _OUT.mkdir(parents=True, exist_ok=True)
    p = _OUT / f"qwen_{voice}_{int(time.time())}.mp3"
    p.write_bytes(_b64.b64decode(audio))
    return p


VOICE_PROMPTS = {
    "A": "青年女性（19-25岁），中音，语速偏慢，音色干净自然，带一点沉稳和不易察觉的倦意；"
         "情绪稳定，不甜不嗲不做作，像想事情的人在说话；适合日常陪伴聊天。",
    "B": "青年女性，音色清亮偏中，语速中等偏慢，安静邻家感，不活泼；"
         "句尾自然放轻，像会静静地听人说话的人；适合深夜聊天。",
}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if not key():
        print("缺少 DASHSCOPE_API_KEY")
        sys.exit(1)
    for name, prompt in VOICE_PROMPTS.items():
        try:
            vid = design_voice(prompt)
            print(f"{name}: voice_id={vid[:24]}…")
            mp3 = synth("嗯……今天忙完了没有？", vid)
            print(f"   样句 → {mp3.name}")
        except Exception as e:
            print(f"{name}: FAIL {str(e)[:160]}")
