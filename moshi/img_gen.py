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
MODEL_DIR = _ROOT / "tmp_cosy" / "models" / "RealVisXL_V4.0"
PHOTO_DIR = _ROOT / "data" / "photo_cache"
STATIC_DIR = _ROOT / "data" / "static"

_pipe = None


def available() -> bool:
    return MODEL_DIR.exists() and (MODEL_DIR / "model_index.json").exists()


def _get_pipe():
    global _pipe
    if _pipe is not None:
        return _pipe
    if not available():
        raise RuntimeError("本地生图模型未就绪（RealVisXL_V4.0）——请先完成下载")
    import torch
    from diffusers import StableDiffusionXLPipeline
    print("[img_gen] 加载 SDXL 模型（首次较慢）…", flush=True)
    t0 = time.time()
    pipe = StableDiffusionXLPipeline.from_pretrained(
        str(MODEL_DIR), torch_dtype=torch.float16, use_safetensors=True)
    pipe.enable_attention_slicing()
    pipe.enable_vae_slicing()
    pipe.enable_model_cpu_offload()
    _pipe = pipe
    print(f"[img_gen] 模型就绪（{time.time() - t0:.0f}s）", flush=True)
    return _pipe


def img2img(base: Path, prompt: str, negative: str,
            strength: float = 0.55, seed: int = 42,
            steps: int = 32, guidance: float = 5.0) -> Path:
    """本体图 → 变体（她的照片）。strength=重绘幅度（越低越保脸）。"""
    pipe = _get_pipe()
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(f"{base.name}|{prompt}|{strength}|{seed}".encode("utf-8")).hexdigest()[:12]
    out = PHOTO_DIR / f"photo_{key}.png"
    if out.exists():
        return out
    import torch
    from PIL import Image
    init = Image.open(base).convert("RGB")
    if min(init.size) < 1024:
        # 放大到 1024 底（图生图输入；本体图通常够大）
        init = init.resize((1024, 1024), Image.LANCZOS)
    gen = torch.Generator(device="cpu").manual_seed(seed)
    t0 = time.time()
    img = pipe(prompt=prompt, negative_prompt=negative, image=init,
               strength=strength, guidance_scale=guidance,
               num_inference_steps=steps, generator=gen).images[0]
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
