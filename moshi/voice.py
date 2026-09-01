"""V4+ 声音（voice）—— 她可以说话（像真人：这轮发文字还是语音，**她选**）。

需求（协作方 2026-09-01）：她像真人一样选择发文字或发语音；**发文字→纯文字；发语音→仅有语音**。

引擎（可换；自动选择）：
- **MiMo VoiceDesign（默认）**：小米 MiMo TTS 音色设计模型（mimo-v2.5-tts-voicedesign）——
  用"音色设计文本"生成**专门的她**的声音（同一份设计文本 → 同一种声音，近似稳定）；
  OpenAI 兼容接口：POST /v1/chat/completions，messages=[{user: 音色设计}, {assistant: 要念的文本}]，
  audio.format=mp3 → choices[0].message.audio.data（base64）。密钥：config/secrets.json 的 MIMO_API_KEY。
- **Edge TTS（兜底）**：免费；音色 zh-CN-XiaoxiaoNeural，语速 -12%，音调 -3Hz。

- 格式：QQ 官方要求 silk（file_type=3）：ffmpeg(mp3→pcm) + tools/silk_encoder.exe(pcm→silk)；
- 选择：`decide_voice()` —— 机制决定（性格/关系/她此刻的日子/这轮的场合），非随机敷衍：
  * 长话 → 打字（真人长话用文字）；
  * 生气/倦怠 → 文字，甚至沉默（冷冰冰更真实）；
  * 她主动想你 → 高概率语音（"想你了"要能听见）；
  * 你敞开心扉/她回应你的心事 → 更愿出声（这时语音比打字近）；
  * 她日子紧（烦/累）→ 更少开口。
- 缓存：data/voice_cache/（gitignore 覆盖 data/）。

依赖：edge-tts（pip）；ffmpeg 与 tools/silk_encoder.exe（本仓库已带，编译自 foyoux/silk-codec =
kn007 SILK SDK 源，Skype 许可，仅自用）。MiMo 走标准库 urllib。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import random
import subprocess
import tempfile
import urllib.request
from pathlib import Path

try:
    import edge_tts
except Exception:
    edge_tts = None

# ── MiMo VoiceDesign（默认引擎）──
MIMO_BASE = "https://api.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5-tts-voicedesign"

# ── 音色候选（设计文本 = 生成"她的声音"的配方；同一份文本 → 同一种声音）──
VOICE_DESIGNS: dict[str, str] = {
    "A": (
        "二十多岁的中国女性，声音平静内敛，语气克制，语速偏慢，音量不大。"
        "音色中低，略带一点清冷和极轻的沙哑，像安静地、想着事情说话；"
        "不甜、不撒娇、不刻意温柔，情绪起伏小，偶尔有一声轻轻的叹息。"
    ),
    "B": (
        "二十多岁的中国女性，声音干净自然，中低音色，语速适中偏慢。"
        "说话带一点点疏离感但不出冷，像安静温柔的邻家姐姐；"
        "平实、耐听、没有表演感，偶尔在句尾轻轻放下来。"
    ),
    "C": (
        "二十多岁的中国女性，声音轻、低、软但克制，语速较慢，音量偏小。"
        "像深夜压低声音跟你说的话，安静、让人安心，不情绪化，"
        "话不多，但每句都落得很稳。"
    ),
}
VOICE_DESIGN_DEFAULT = "A"   # 候选音频试听后，把选中的字母定在这里

# Edge 兜底参数（MiMo 未配置时才用）
EDGE_VOICE = "zh-CN-XiaoxiaoNeural"
EDGE_RATE = "-12%"
EDGE_PITCH = "-3Hz"

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
_SILK_ENC = _TOOLS / "silk_encoder.exe"
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "voice_cache"
_SECRETS = Path(__file__).resolve().parents[1] / "config" / "secrets.json"


def mimo_key() -> str:
    """MiMo TTS 密钥：环境变量 MIMO_API_KEY → config/secrets.json。"""
    env = os.environ.get("MIMO_API_KEY", "").strip()
    if env:
        return env
    try:
        if _SECRETS.exists():
            v = (json.loads(_SECRETS.read_text(encoding="utf-8")).get("MIMO_API_KEY") or "").strip()
            if v and not v.startswith("在此"):
                return v
    except Exception:
        pass
    return ""


def synth_text(text: str, voice_design: str | None = None) -> Path:
    """合成一句话 → mp3（引擎自动选择：MiMo 配了密钥用 MiMo（她的专有音色），否则 Edge 兜底）。"""
    if mimo_key():
        return synth_mimo(text, voice_design or VOICE_DESIGN_DEFAULT)
    if edge_tts is None:
        raise RuntimeError("未配置 MiMo 密钥且 edge-tts 未安装")
    return synth_edge(text)


def synth_mimo(text: str, voice_design: str) -> Path:
    """MiMo VoiceDesign：user=音色设计文本，assistant=要念的文本（OpenAI 兼容）。"""
    payload = {
        "model": MIMO_MODEL,
        "messages": [
            {"role": "user", "content": VOICE_DESIGNS.get(voice_design, voice_design)},
            {"role": "assistant", "content": text},
        ],
        "audio": {"format": "mp3"},
    }
    req = urllib.request.Request(
        f"{MIMO_BASE}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {mimo_key()}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    b64 = data["choices"][0]["message"]["audio"]["data"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"mimo_{voice_design}_{hashlib.md5(text.encode('utf-8')).hexdigest()[:10]}.mp3"
    path.write_bytes(base64.b64decode(b64))
    return path


def synth_edge(text: str) -> Path:
    """Edge TTS（兜底）。"""
    out_dir = CACHE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"tts_{hashlib.md5((EDGE_VOICE + text).encode('utf-8')).hexdigest()[:12]}.mp3"
    if path.exists() and path.stat().st_size > 0:
        return path
    async def _go() -> None:
        c = edge_tts.Communicate(text, voice=EDGE_VOICE, rate=EDGE_RATE, pitch=EDGE_PITCH)
        await c.save(str(path))
    asyncio.run(_go())
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("edge-tts 合成失败（网络/音色不可用）")
    return path


def _ffmpeg() -> str:
    try:
        # 系统 ffmpeg 优先（本项目环境已验证 ffmpeg 8.1.1）
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return "ffmpeg"
    except Exception:
        pass
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


# ── 合成 ──
def synth_mp3(text: str, out_dir: Path | None = None) -> Path:
    """她的一句话 → mp3 文件。"""
    out_dir = out_dir or CACHE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"tts_{hashlib.md5((VOICE + text).encode('utf-8')).hexdigest()[:12]}.mp3"
    if path.exists() and path.stat().st_size > 0:
        return path
    async def _go() -> None:
        c = edge_tts.Communicate(text, voice=VOICE, rate=RATE, pitch=PITCH)
        await c.save(str(path))
    asyncio.run(_go())
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("edge-tts 合成失败（网络/音色不可用）")
    return path


def mp3_to_silk(mp3_path: Path) -> Path:
    """mp3 → silk（QQ 官方语音格式）：ffmpeg 转 24kHz 单声道 PCM → silk_encoder.exe。"""
    if not _SILK_ENC.exists():
        raise RuntimeError(f"缺少 {_SILK_ENC}（tools/silk_encoder.exe）")
    with tempfile.TemporaryDirectory() as td:
        pcm = Path(td) / "v.pcm"
        ff = _ffmpeg()
        if not ff:
            raise RuntimeError("缺少 ffmpeg")
        r = subprocess.run([ff, "-y", "-i", str(mp3_path), "-ar", "24000", "-ac", "1",
                            "-f", "s16le", str(pcm)], capture_output=True)
        if not pcm.exists() or pcm.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg 转 pcm 失败: {r.stderr.decode('utf-8', 'ignore')[-200:]}")
        silk = CACHE_DIR / (mp3_path.stem + ".silk")
        silk.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([str(_SILK_ENC), str(pcm), str(silk)], capture_output=True)
        if not silk.exists() or silk.stat().st_size == 0:
            raise RuntimeError(f"silk 编码失败: {r.stdout.decode('utf-8', 'ignore')[-200:]}")
        return silk


def ensure_silk(text: str, voice_design: str | None = None) -> Path:
    """她的一句话 → silk 文件（带缓存；合成引擎自动选择）。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    design = voice_design or VOICE_DESIGN_DEFAULT
    key = hashlib.md5((design + text).encode("utf-8")).hexdigest()[:12]
    silk = CACHE_DIR / f"v_{key}.silk"
    if silk.exists() and silk.stat().st_size > 0:
        return silk
    return mp3_to_silk(synth_text(text, voice_design=design))


# ── 她选文字还是语音（像真人：机制决定，非随机敷衍）──
def decide_voice(person, intent: str, reply: str, turn_kind: str = "reply") -> bool:
    """这一轮她【发语音】吗？决策依据：
    - 场合：她主动想你（touch）→ 最想出声；你敞开心扉/她认真回应心事 → 出声更近；
    - 人格：初识少出声；关系越深越自然；生气/倦怠 → 文字甚至沉默；
    - 她的日子：烦/累 → 更少开口（心情真的会影响）；
    - 长度：长话打字（真人如此）。
    Deterministic：`Random(f"{seed}:voice:{interaction_count}")`（同条件同选择，可复现）。
    """
    if not reply or not reply.strip():
        return False
    if len(reply) > 60:                       # 长话 → 打字
        return False
    if getattr(person, "is_angry", False) or getattr(person, "exhausted", False):
        return False                          # 生气/倦怠 → 文字，甚至沉默
    try:
        stage = person.relationship_stage()
    except Exception:
        stage = "初识"
    base = {"初识": 0.05, "熟悉": 0.12, "亲近": 0.22, "深入": 0.28}.get(stage, 0.08)
    if turn_kind == "touch":
        base += 0.45                          # 她想你时 → 语音（"想你了"要能听见）
    if intent in ("user_share", "comfort", "ask_past"):
        base += 0.15                          # 回应你的心事 → 更愿出声
    mood = getattr(person, "life_mood", "") or ""
    if any(k in mood for k in ("烦", "累", "提不起劲")):
        base -= 0.10                          # 她日子紧 → 更少开口
    p = max(0.02, min(0.85, base))
    try:
        n = int(getattr(person, "interaction_count", 0) or 0)
    except Exception:
        n = 0
    # 盐 = 种子×相处次数×这句话（同话同判、异话异判——像真人"这句想/不想说出来"）
    rng = random.Random(f"{getattr(person, 'seed', 0)}:voice:{n}:{reply.strip()[:24]}")
    return rng.random() < p


def describe_voice() -> str:
    """她声音的"设定"（供文档/调试；不是她自我盘点）。"""
    if mimo_key():
        return (f"MiMo VoiceDesign · 候选「{VOICE_DESIGN_DEFAULT}」"
                f"（{VOICE_DESIGNS.get(VOICE_DESIGN_DEFAULT, '')[:30]}…）")
    return f"Edge TTS · {EDGE_VOICE}（语速 {EDGE_RATE}，音调 {EDGE_PITCH}）——平静、略慢、不甜不嗲（兜底）"
