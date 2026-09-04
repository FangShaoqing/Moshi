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


def synth(text: str, voice_id: str, model: str | None = None) -> Path:
    """设计音色合成 → mp3（multimodal-generation/generation）。"""
    m = model or VD_MODEL
    d = _post({"model": m, "input": {"text": text, "voice": voice_id}})
    out = d.get("output", d)
    audio = None
    if isinstance(out, dict):
        a = out.get("audio")
        if isinstance(a, dict):
            audio = a.get("data") or a.get("url")     # OSS url（实际返回 dict）
        else:
            audio = a or out.get("audio_url") or out.get("url")
    # 兼容直接 base64 字符串
    if isinstance(audio, str) and audio.startswith("http"):
        with urllib.request.urlopen(audio, timeout=120) as r:
            raw = r.read()
        b64 = "base64," + __import__("base64").b64encode(raw).decode()
        audio = b64
    b64 = None
    if isinstance(audio, str) and audio.startswith("base64,"):
        b64 = audio[len("base64,"):]
    elif isinstance(audio, str):
        b64 = audio
    if not b64:
        raise RuntimeError(f"合成无音频: {json.dumps(d, ensure_ascii=False)[:200]}")
    _OUT.mkdir(parents=True, exist_ok=True)
    p = _OUT / f"qwenvd_{voice_id[:12]}_{int(time.time())}.mp3"
    p.write_bytes(base64.b64decode(b64))
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
