"""本地生图（img_gen）—— SDXL（RealVisXL）图生图：她的本体图 → 她日子的照片。

- 懒加载：首次生成才装模型（qqbot 启动不受影响，第一次生图会慢 ~1-2 分钟）；
- 4GB 显存策略：fp16 + attention/vae slicing + model_cpu_offload（~30-90s/张）；
- 确定性：seed 固定（同场景同结果；换 seed 出变体）；
- 产出：data/photo_cache/*.png（QQ 经同一个静态文件服务拉取）。
"""

from __future__ import annotations

import hashlib
import random
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = _ROOT / "tmp_cosy" / "models" / "dreamshaper-8"              # SD1.5（备选，目录形态）
SDXL_DIR = _ROOT / "tmp_cosy" / "models" / "RealVisXL_V4.0"             # SDXL（画质慢路线，备用）
RV51_FILE = next(_ROOT.glob("tmp_cosy/cache_rv51/**/Realistic_Vision_V5.1.safetensors"), None)
MJ_FILE = next(_ROOT.glob("tmp_cosy/models/majicMIX_realistic_v7/majicmixRealistic_v7.safetensors"), None)
PHOTO_DIR = _ROOT / "data" / "photo_cache"
STATIC_DIR = _ROOT / "data" / "static"

_pipe = None
_MODEL_REV = ""       # 当前加载的模型名（缓存键区分模型，换模型=新图）


def available() -> bool:
    return MODEL_DIR.exists() and (MODEL_DIR / "model_index.json").exists()


def _get_pipe():
    global _pipe
    if _pipe is not None:
        return _pipe
    if not available():
        raise RuntimeError("本地生图模型未就绪（majicMIX/dreamshaper）——请先完成下载")
    import torch
    from diffusers import StableDiffusionPipeline
    print("[img_gen] 加载 SD1.5 写实模型（首次较慢）…", flush=True)
    t0 = time.time()
    if MJ_FILE is not None:
        # 首选：majicMIX realistic v7（更写实；单文件含 VAE；实测无 NSFW 跑偏）
        pipe = StableDiffusionPipeline.from_single_file(
            str(MJ_FILE), torch_dtype=torch.float16, safety_checker=None)
    else:
        pipe = StableDiffusionPipeline.from_pretrained(
            str(MODEL_DIR), torch_dtype=torch.float16, variant="fp16",
            use_safetensors=True, local_files_only=True,
            safety_checker=None)      # diffusers 的 NSFW 粗筛对写实人像极易误判（黑图）；关掉（图仅自用）
    if torch.cuda.is_available():
        pipe = pipe.to("cuda")            # 4GB：fp16 整卡装得下（~3.4GB）；必须显式搬 GPU
    pipe.enable_attention_slicing()
    pipe.enable_vae_slicing()
    _pipe = pipe
    global _MODEL_REV
    _MODEL_REV = "majicMIX_v7" if MJ_FILE is not None else MODEL_DIR.name
    print(f"[img_gen] 模型就绪（{time.time() - t0:.0f}s）", flush=True)
    return _pipe


def txt2img(prompt: str, negative: str,
            seed: int = 42, steps: int = 32, guidance: float = 7.0) -> Path:
    """文生图（她的视角照片：没有人脸需要锚定，纯世界/静物/背影）。"""
    pipe = _get_pipe()
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(f"txt|{_MODEL_REV}|{prompt}|{seed}".encode("utf-8")).hexdigest()[:12]
    out = PHOTO_DIR / f"photo_{key}.png"
    if out.exists():
        return out
    import torch
    gen = torch.Generator(device="cpu").manual_seed(seed)
    t0 = time.time()
    img = pipe(prompt=prompt, negative_prompt=negative,
               guidance_scale=guidance, num_inference_steps=steps, generator=gen,
               width=640, height=832).images[0]      # 竖图（手机照片比例）
    img.save(out)
    print(f"[img_gen] 生成完成 {time.time() - t0:.0f}s → {out.name}", flush=True)
    return out


def img2img(base: Path, prompt: str, negative: str,
            strength: float = 0.55, seed: int = 42,
            steps: int = 32, guidance: float = 5.0) -> Path:
    """本体图 → 变体（她的照片）。strength=重绘幅度（越低越保脸）。"""
    pipe = _get_pipe()
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(f"{base.name}|{_MODEL_REV}|{prompt}|{strength}|{seed}".encode("utf-8")).hexdigest()[:12]
    out = PHOTO_DIR / f"photo_{key}.png"
    if out.exists():
        return out
    import torch
    from PIL import Image
    init = Image.open(base).convert("RGB")
    if min(init.size) < 512:
        init = init.resize((640, 832), Image.LANCZOS)
    gen = torch.Generator(device="cpu").manual_seed(seed)
    t0 = time.time()
    img = pipe(prompt=prompt, negative_prompt=negative, image=init,
               strength=strength, guidance_scale=guidance,
               num_inference_steps=steps, generator=gen,
               width=640, height=832).images[0]      # 竖图（手机照片比例）
    img.save(out)
    print(f"[img_gen] 生成完成 {time.time() - t0:.0f}s → {out.name}", flush=True)
    return out


def base_image() -> Path | None:
    """她的本体图（用户提供 data/static/her_base.png；没有则 None）。"""
    for name in ("her_base.png", "her_base.jpg", "her_base.jpeg"):
        p = STATIC_DIR / name
        if p.exists():
            return p
    return None
