"""临时：知归话池生成（Sambert 原声 + 心情节奏微调）；验证后删除"""
import sys, subprocess
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"D:\FangShaoqing\Moshi\ChenMoshi")
from pathlib import Path
import dashscope
from moshi.sambert_audition import key

dashscope.api_key = key()
OUT = Path(r"D:\FangShaoqing\Moshi\ChenMoshi\data\voice_cache")

# 句 → (文本, rate, pitch) —— 心情映射（她平淡，波动很小）
POOL = {
    "s1_check":  ("嗯……今天忙完了没有？", 1.0, 1.0),
    "s2_miss":   ("有点想你。[quick_breath]……没事，我就是说一声。".replace("[quick_breath]", "嗯，"), 0.9, 0.94),
    "s3_rain":   ("今天下雨了。你那边呢？", 0.98, 1.0),
    "s4_low":    ("我在。……我有点睡不着。", 0.88, 0.92),
    "s5_care":   ("你最近怎么样。……嗯，就是想问问。", 0.95, 0.97),
}

for name, (text, rate, pitch) in POOL.items():
    r = dashscope.SpeechSynthesizer.call(model="sambert-zhigui-v1", text=text,
                                         format="mp3", sample_rate=48000,
                                         rate=rate, pitch=pitch)
    resp = r.get_response() or {}
    if resp.get("status_code") != 200:
        print("FAIL", name, resp.get("status_code"), str(resp.get("message"))[:80]); continue
    mp3 = OUT / f"zhgui_{name}.mp3"
    mp3.write_bytes(r.get_audio_data())
    print("✅", name, "→", mp3.name, f"(rate={rate}, pitch={pitch})")
