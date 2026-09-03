"""临时压力测试：照片场景池稳定性（人像哨兵过滤；验证后删除）"""
import sys, time
sys.path.insert(0, r"D:\FangShaoqing\Moshi\ChenMoshi")
from moshi import img_gen
from moshi import photo as P
from pathlib import Path

REPORT: dict[str, dict] = {}

for scene, body in P.SCENES.items():
    prompt = f"{body}, still life, {P.PHOTO_STYLE}"
    passed = 0
    notes = []
    for seed in (11, 22, 33):
        try:
            out = img_gen.txt2img(prompt, P.NEGATIVE, seed=seed)
            if P._has_person(out):
                notes.append(f"seed{seed}:有人")
            else:
                notes.append(f"seed{seed}:无人")
                passed += 1
        except Exception as e:
            notes.append(f"seed{seed}:异常{str(e)[:40]}")
    REPORT[scene] = {"passed": passed, "notes": notes}
    print(f"{scene}: {passed}/3  →  {' / '.join(notes)}", flush=True)

print("\n=== 结论 ===")
for scene, r in REPORT.items():
    mark = "✅ 稳定" if r["passed"] >= 2 else ("⚠️ 一半" if r["passed"] else "❌ 放弃")
    print(f"{mark:<8} {scene}")
