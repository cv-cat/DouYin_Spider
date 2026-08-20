# coding=utf-8
"""批量跑视频逐帧分析，生成 HTML 报告。默认只跑爆款前 N 个（按 digg_count 排序）。"""
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.video_analyzer import analyze_video, generate_html_report, _get_video_info

MEDIA_DIR = sys.argv[1] if len(sys.argv) > 1 else "datas/media_datas/野阪泉_65935844129"
TOP_N = int(sys.argv[2]) if len(sys.argv) > 2 else 5
OUTPUT_DIR = "datas/analysis_reports"
USER_NAME = "野阪泉"
MAX_FRAMES = 30

os.makedirs(OUTPUT_DIR, exist_ok=True)

# 先按点赞排序，选 top N，避免全量分析
candidates = []
for name in sorted(os.listdir(MEDIA_DIR)):
    dir_path = os.path.join(MEDIA_DIR, name)
    if not os.path.isdir(dir_path) or name.startswith("."):
        continue
    vp, ip = os.path.join(dir_path, "video.mp4"), os.path.join(dir_path, "info.json")
    if not os.path.exists(vp) or not os.path.exists(ip):
        continue
    try:
        meta = json.load(open(ip, encoding="utf-8"))
    except Exception:
        meta = {}
    candidates.append((meta.get("digg_count", 0), name, dir_path, vp, ip, meta))

candidates.sort(reverse=True, key=lambda x: x[0])
selected = candidates[:TOP_N]
print(f"=== 共 {len(candidates)} 个视频，选取爆款前 {len(selected)} 个 ===", flush=True)
for i, (d, name, *_rest) in enumerate(selected):
    print(f"  #{i+1}  赞={d}  {name[:40]}", flush=True)

# 逐个分析
results = []
t0 = datetime.now()
for i, (d, name, dir_path, vp, ip, meta) in enumerate(selected):
    print(f"[{i+1}/{len(selected)}] 开始: {name[:40]}", flush=True)
    try:
        duration = _get_video_info(vp)["duration"]
        frame_interval = max(3, int(duration / MAX_FRAMES)) if duration > 0 else 5
        analysis = analyze_video(vp, ip, frame_interval=frame_interval)
        analysis["dir_name"] = name
        results.append(analysis)
    except Exception as e:
        print(f"  分析失败 {name}: {e}", flush=True)

elapsed = (datetime.now() - t0).total_seconds()
if not results:
    print("REPORT_FAIL: 无成功分析的视频", flush=True)
    sys.exit(1)

results.sort(key=lambda x: x.get("meta", {}).get("digg_count", 0), reverse=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_path = os.path.join(OUTPUT_DIR, f"{USER_NAME}_top{len(results)}_{timestamp}.html")
generate_html_report(results, output_path, USER_NAME)

video_count = sum(1 for a in results if a["video_info"]["duration"] > 0)
total_likes = sum(a.get("meta", {}).get("digg_count", 0) for a in results)
total_frames = sum(a.get("frame_stats", {}).get("total_frames", 0) for a in results)
print(f"REPORT_DONE: {output_path}", flush=True)
print(f"SUMMARY: videos={video_count} likes={total_likes} frames={total_frames} elapsed={elapsed:.0f}s", flush=True)
