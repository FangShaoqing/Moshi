"""V4+ 声音（voice）—— 她可以说话（像真人：这轮发文字还是语音，**她选**）。

需求（协作方 2026-09-01）：她像真人一样选择发文字或发语音；**发文字→纯文字；发语音→仅有语音**。

- 合成：edge-tts（免费；音色 zh-CN-XiaoxiaoNeural，语速 -12%，音调 -3Hz——不甜不嗲，配她
  的沉静；Xiaohan 等音色已在 edge 服务下线，Xiaoxiao 可用）；
- 格式：QQ 官方要求 silk（file_type=3）：ffmpeg(mp3→pcm) + tools/silk_encoder.exe(pcm→silk)；
- 选择：`decide_voice()` —— 机制决定（性格/关系统/她此刻的日子/这轮的场合），非随机敷衍：
  * 长话 → 打字（真人长话用文字）；
  * 生气/倦怠 → 文字，甚至沉默（冷冰冰更真实）；
  * 她主动想你 → 高概率语音（"想你了"要能听见）；
  * 你敞开心扉/她回应你的心事 → 更愿出声（这时语音比打字近）；
  * 她日子紧（烦/累）→ 更少开口。
- 缓存：data/voice_cache/（gitignore 覆盖 data/）。

依赖：edge-tts（pip）；ffmpeg 与 tools/silk_encoder.exe（本仓库已带，编译自 foyoux/silk-codec =
kn007 SILK SDK 源，Skype 许可，仅自用）。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts

# 音色（配她：沉静内敛，不甜不嗲）
VOICE = "zh-CN-XiaoxiaoNeural"
RATE = "-12%"       # 语速稍慢（她话不多，也不急）
PITCH = "-3Hz"      # 音调略低（更平静，不嗲）

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
_SILK_ENC = _TOOLS / "silk_encoder.exe"
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "voice_cache"


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


def ensure_silk(text: str) -> Path:
    """她的一句话 → silk 文件（带缓存）。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5((VOICE + text).encode("utf-8")).hexdigest()[:12]
    silk = CACHE_DIR / f"v_{key}.silk"
    if silk.exists() and silk.stat().st_size > 0:
        return silk
    return mp3_to_silk(synth_mp3(text))


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
    return f"Edge TTS · {VOICE}（语速 {RATE}，音调 {PITCH}）——平静、略慢、不甜不嗲"
