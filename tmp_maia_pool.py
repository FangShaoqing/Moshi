"""临时：Maia（四月）话池 5 句（qwen3-tts-flash/instruct + 心情指令）；验证后删除"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"D:\FangShaoqing\Moshi\ChenMoshi")
from moshi.qwen_tts import synth_flash

POOL = {
    "s1_check": ("嗯……今天忙完了没有？",
                 "很自然地说话，平常语气，语速正常偏慢一点，句尾轻轻落下来。"),
    "s2_miss": ("有点想你。嗯，没事，我就是说一声。",
                "声音更柔和一点，语速偏慢，像夜里想起一个人，问句像真的关心。"),
    "s3_rain": ("今天下雨了。你那边呢？",
                "平常语气，带一点描述天气的平静，问句自然，不生硬。"),
    "s4_low": ("我在。……我有点睡不着。",
               "语速再慢一点，声音压低一些，带一点疲惫感，中间像真的有话停了一下。"),
    "s5_care": ("你最近怎么样。嗯，就是想问问。",
                "温和，语速中等，句尾轻轻放轻，像随口一问又不敷衍。"),
}

for name, (text, ins) in POOL.items():
    try:
        p = synth_flash(text, voice="Maia", instructions=ins)
        print("✅", name, "→", p.name)
    except Exception as e:
        print("❌", name, str(e)[:140])
