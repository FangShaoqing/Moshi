"""语音识别（asr）—— 百炼 Paraformer：她"听"你发的语音（QQ 语音文件 → 文字）。

- 接口：POST /api/v1/services/speech/asr/recognition
  {"model": "paraformer-realtime-v2", "input": {"file_urls": [URL]}, "parameters": {...}}
- QQ 语音消息自带公网临时 URL → 直接丢给 Paraformer（免上传）；
- 无 key/失败 → None（她诚实地"没听清"）。

注意：QQ 官方无 ASR 接口；Paraformer 中文识别质量好，免费额度（36K tokens）或按量约 0.1-0.3 元/小时。
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_KEY_FILE = _ROOT / "config" / "secrets.json"

URL = "https://dashscope.aliyuncs.com/api/v1/services/speech/asr/recognition"
MODEL = "paraformer-realtime-v2"


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


def recognize_url(audio_url: str) -> str | None:
    """识别公网音频 URL（QQ 语音临时链接）。返回文字或 None。"""
    if not key():
        return None
    payload = {"model": MODEL,
               "input": {"file_urls": [audio_url]},
               "parameters": {"format": "silk", "sample_rate": 24000, "enable_itn": True}}
    try:
        req = urllib.request.Request(URL, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {key()}"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode("utf-8"))
        sentences = (d.get("output") or {}).get("sentences") or []
        text = "".join(s.get("text", "") for s in sentences).strip()
        return text or None
    except Exception as e:
        print(f"[asr] 识别失败：{str(e)[:120]}")
        return None
