# coding=utf-8
"""
视频逐帧分析模块
提供场景检测、音频分析、节奏分析、HTML 可视化报告生成能力
依赖: ffmpeg (需在 PATH 中或通过 FFMPEG_BIN 环境变量指定)
"""

import json
import math
import os
import re
import subprocess
import base64
import tempfile
import shutil
from datetime import datetime
from collections import Counter
from loguru import logger

# ffmpeg 路径 — 自动检测 brew 安装路径
_FFMPEG_CANDIDATES = [
    os.environ.get("FFMPEG_BIN", ""),
    "/usr/local/Cellar/ffmpeg/9.0.1/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/opt/homebrew/bin/ffmpeg",
    "ffmpeg",
]
FFMPEG = None
for _c in _FFMPEG_CANDIDATES:
    if _c and shutil.which(_c):
        FFMPEG = _c
        break
if FFMPEG is None:
    FFMPEG = "ffmpeg"  # fallback, will error if not found

# ffprobe 路径 — 优先与 ffmpeg 同目录
FFPROBE = None
if FFMPEG and FFMPEG.endswith("ffmpeg"):
    _ffp = FFMPEG[:-6] + "ffprobe"
    if shutil.which(_ffp):
        FFPROBE = _ffp
if FFPROBE is None:
    FFPROBE = shutil.which("ffprobe") or "ffprobe"


def _run_ffmpeg(args, timeout=120):
    """运行 ffmpeg 命令，返回 stdout"""
    try:
        result = subprocess.run(
            [FFMPEG] + args,
            capture_output=True, text=True, timeout=timeout
        )
        return result.stderr + result.stdout  # ffmpeg 主要输出到 stderr
    except subprocess.TimeoutExpired:
        logger.warning(f"ffmpeg 超时: {' '.join(args[:5])}...")
        return ""
    except FileNotFoundError:
        logger.error(f"ffmpeg 未找到，请安装 ffmpeg 或设置 FFMPEG_BIN 环境变量")
        raise


def _run_ffprobe(args, timeout=60):
    """运行 ffprobe 命令，返回 stdout（JSON）"""
    try:
        result = subprocess.run(
            [FFPROBE] + args,
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        logger.warning(f"ffprobe 超时: {' '.join(args[:5])}...")
        return ""
    except FileNotFoundError:
        logger.error("ffprobe 未找到，请安装 ffmpeg 或设置 FFMPEG_BIN 环境变量")
        return ""


def _parse_fps(rate_str):
    """解析 ffprobe 帧率字符串，如 '30000/1001' → float"""
    if not rate_str or rate_str in ("0/0", "N/A"):
        return 0.0
    try:
        if "/" in rate_str:
            num, den = rate_str.split("/")
            den = float(den)
            return float(num) / den if den else 0.0
        return float(rate_str)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _get_video_info(video_path):
    """获取视频基本信息：时长、分辨率、帧率、码率（ffprobe JSON，正则兜底）"""
    info = {"duration": 0, "width": 0, "height": 0, "fps": 0, "bitrate": 0, "codec": "",
            "nb_frames": 0, "pix_fmt": ""}

    # 优先 ffprobe JSON
    try:
        raw = _run_ffprobe([
            "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", video_path
        ], timeout=30)
        if raw:
            data = json.loads(raw)
            fmt = data.get("format", {})
            info["duration"] = float(fmt.get("duration") or 0)
            info["bitrate"] = int(float(fmt.get("bit_rate") or 0) / 1000)  # → kb/s
            for s in data.get("streams", []):
                if s.get("codec_type") == "video":
                    info["codec"] = s.get("codec_name", "")
                    info["width"] = int(s.get("width") or 0)
                    info["height"] = int(s.get("height") or 0)
                    info["fps"] = _parse_fps(s.get("avg_frame_rate")) or _parse_fps(s.get("r_frame_rate"))
                    if not info["bitrate"]:
                        info["bitrate"] = int(float(s.get("bit_rate") or 0) / 1000)
                    nb = s.get("nb_frames")
                    if nb and nb != "N/A":
                        info["nb_frames"] = int(nb)
                    info["pix_fmt"] = s.get("pix_fmt", "")
                    if not info["duration"]:  # 流级时长兜底
                        info["duration"] = float(s.get("duration") or 0)
                    break
            if info["duration"] or info["width"]:
                return info
    except (json.JSONDecodeError, ValueError) as e:
        logger.debug(f"ffprobe JSON 解析失败，回退正则: {e}")

    # 正则兜底
    output = _run_ffmpeg(["-i", video_path], timeout=30)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", output)
    if m:
        info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(r"Video:\s*(\S+)", output)
    if m:
        info["codec"] = m.group(1)
    m = re.search(r"(\d+)x(\d+)", output)
    if m:
        info["width"] = int(m.group(1))
        info["height"] = int(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*fps", output)
    if m:
        info["fps"] = float(m.group(1))
    m = re.search(r"(\d+)\s*kb/s", output)
    if m:
        info["bitrate"] = int(m.group(1))
    return info


def _get_frame_stats(video_path, duration):
    """统计总帧数与关键帧数（ffprobe 包级元数据，不解码）"""
    stats = {"total_frames": 0, "keyframes": 0, "avg_keyframe_interval": 0.0}
    try:
        raw = _run_ffprobe([
            "-v", "quiet", "-print_format", "json",
            "-show_entries", "packet=flags",
            "-select_streams", "v:0", video_path
        ], timeout=60)
        if not raw:
            return stats
        pkts = json.loads(raw).get("packets", [])
        stats["total_frames"] = len(pkts)
        stats["keyframes"] = sum(1 for p in pkts if p.get("flags", "_")[0] == "K")
        if stats["keyframes"] and duration > 0:
            stats["avg_keyframe_interval"] = round(duration / stats["keyframes"], 1)
    except (json.JSONDecodeError, ValueError) as e:
        logger.debug(f"frame_stats 解析失败: {e}")
    return stats


def _detect_scenes(video_path, threshold=0.3):
    """检测场景切换点，返回切换时间列表（秒）"""
    output = _run_ffmpeg([
        "-i", video_path,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-"
    ], timeout=180)

    cuts = []
    for line in output.split("\n"):
        m = re.search(r"pts_time:(\d+\.?\d*)", line)
        if m:
            t = float(m.group(1))
            if t > 0.1:  # 忽略开头
                cuts.append(round(t, 2))
    return cuts


def _detect_audio_silence(audio_path, threshold=-25, min_duration=0.3):
    """检测音频静音段落（配音断句），返回静音区间列表"""
    output = _run_ffmpeg([
        "-i", audio_path,
        "-af", f"silencedetect=n={threshold}dB:d={min_duration}",
        "-f", "null", "-"
    ], timeout=60)

    silences = []
    start = None
    for line in output.split("\n"):
        m = re.search(r"silence_start:\s*(\d+\.?\d*)", line)
        if m:
            start = float(m.group(1))
        m = re.search(r"silence_end:\s*(\d+\.?\d*)\s*\|\s*silence_duration:\s*(\d+\.?\d*)", line)
        if m and start is not None:
            silences.append({
                "start": round(start, 2),
                "end": round(float(m.group(1)), 2),
                "duration": round(float(m.group(2)), 2)
            })
            start = None
    return silences


def _detect_audio_volume(audio_path):
    """检测音频响度"""
    output = _run_ffmpeg([
        "-i", audio_path,
        "-af", "volumedetect",
        "-f", "null", "-"
    ], timeout=30)

    result = {"mean": None, "max": None}
    m = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", output)
    if m:
        result["mean"] = float(m.group(1))
    m = re.search(r"max_volume:\s*([-\d.]+)\s*dB", output)
    if m:
        result["max"] = float(m.group(1))
    return result


def _generate_contact_sheet(video_path, output_path, interval, duration, cols=6):
    """生成接触印片（单张 jpg 网格），替代逐帧 base64"""
    n = max(1, int(duration / interval) + 1) if duration > 0 else 10
    rows = max(1, math.ceil(n / cols))
    _run_ffmpeg([
        "-y", "-i", video_path,
        "-vf", f"fps=1/{interval},scale=240:-1,tile={cols}x{rows}:margin=2",
        "-frames:v", "1", "-q:v", "3", output_path
    ], timeout=120)
    return output_path


def _file_to_base64(path):
    """读取文件并 base64 编码"""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _analyze_rhythm(cuts, duration):
    """分析节奏：分四段计算镜头频率"""
    if duration <= 0:
        return {}

    segments = [
        ("开场 (0-10%)", 0, duration * 0.1),
        ("叙事 (10-33%)", duration * 0.1, duration * 0.33),
        ("高潮 (33-66%)", duration * 0.33, duration * 0.66),
        ("收尾 (66-100%)", duration * 0.66, duration),
    ]

    result = {}
    for label, start, end in segments:
        seg_cuts = [c for c in cuts if start <= c < end]
        if end == duration:
            seg_cuts = [c for c in cuts if start <= c <= end]
        shot_count = len(seg_cuts) + 1
        seg_dur = end - start
        result[label] = {
            "start": round(start, 1),
            "end": round(end, 1),
            "shots": shot_count,
            "avg_shot_length": round(seg_dur / shot_count, 1) if shot_count > 0 else 0
        }

    # 前 10 秒
    first_10 = [c for c in cuts if c <= 10]
    result["前10秒"] = {
        "start": 0,
        "end": 10,
        "shots": len(first_10) + 1,
        "avg_shot_length": round(10 / (len(first_10) + 1), 1)
    }

    # 全片
    result["全片"] = {
        "start": 0,
        "end": round(duration, 1),
        "shots": len(cuts) + 1,
        "avg_shot_length": round(duration / (len(cuts) + 1), 1) if cuts else duration
    }

    return result


def _read_info_json(info_path):
    """读取 info.json 获取视频元数据"""
    if not os.path.exists(info_path):
        return {}
    with open(info_path, "r", encoding="utf-8") as f:
        return json.load(f)


def analyze_video(video_path, info_json_path=None, frame_interval=3):
    """
    分析单个视频

    Args:
        video_path: 视频文件路径
        info_json_path: info.json 路径（可选）
        frame_interval: 帧提取间隔（秒），默认 3 秒

    Returns:
        dict: 分析结果
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    logger.info(f"开始分析视频: {video_path}")

    # 基本信息
    video_info = _get_video_info(video_path)
    duration = video_info["duration"]

    # 帧级统计（总帧数 / 关键帧分布）
    frame_stats = _get_frame_stats(video_path, duration)

    # 读取元数据
    meta = {}
    if info_json_path and os.path.exists(info_json_path):
        meta = _read_info_json(info_json_path)

    # 场景检测
    cuts = _detect_scenes(video_path)
    logger.info(f"  检测到 {len(cuts)} 个场景切换点")

    # 音频分析（提取音频到临时文件）
    tmpdir = tempfile.mkdtemp(prefix="vlog_analyze_")
    try:
        audio_path = os.path.join(tmpdir, "audio.wav")
        _run_ffmpeg(["-i", video_path, "-vn", "-acodec", "pcm_s16le", audio_path, "-y"], timeout=60)

        silences = _detect_audio_silence(audio_path) if os.path.exists(audio_path) else []
        volume = _detect_audio_volume(audio_path) if os.path.exists(audio_path) else {}
        logger.info(f"  检测到 {len(silences)} 个配音断句")
    except Exception as e:
        logger.warning(f"  音频分析失败: {e}")
        silences = []
        volume = {}

    # 接触印片（单张网格图，替代逐帧 base64）
    contact_sheet_b64 = ""
    try:
        cs_path = os.path.join(tmpdir, "contact_sheet.jpg")
        _generate_contact_sheet(video_path, cs_path, frame_interval, duration)
        if os.path.exists(cs_path) and os.path.getsize(cs_path) > 0:
            contact_sheet_b64 = _file_to_base64(cs_path)
            logger.info(f"  生成接触印片: {os.path.getsize(cs_path) // 1024}KB")
    except Exception as e:
        logger.warning(f"  接触印片生成失败: {e}")

    # 节奏分析
    rhythm = _analyze_rhythm(cuts, duration)

    # 清理临时文件
    shutil.rmtree(tmpdir, ignore_errors=True)

    result = {
        "video_info": video_info,
        "meta": meta,
        "cuts": cuts,
        "silences": silences,
        "volume": volume,
        "contact_sheet_b64": contact_sheet_b64,
        "frame_stats": frame_stats,
        "frame_interval": frame_interval,
        "rhythm": rhythm,
        "total_shots": len(cuts) + 1,
        "avg_shot_length": round(duration / (len(cuts) + 1), 1) if cuts else duration,
    }

    logger.info(f"  分析完成: {video_info['duration']:.0f}秒, {len(cuts)+1}镜头, 平均{result['avg_shot_length']}秒/镜头")
    return result


def analyze_user_videos(media_dir, max_frames_per_video=30):
    """
    分析用户目录下所有视频

    Args:
        media_dir: 用户媒体目录路径（如 datas/media_datas/野阪泉_xxx/）
        max_frames_per_video: 每个视频最多嵌入的关键帧数量

    Returns:
        list[dict]: 按点赞数降序排列的分析结果列表
    """
    results = []
    if not os.path.isdir(media_dir):
        logger.error(f"目录不存在: {media_dir}")
        return results

    for dir_name in sorted(os.listdir(media_dir)):
        if dir_name == ".DS_Store":
            continue
        dir_path = os.path.join(media_dir, dir_name)
        if not os.path.isdir(dir_path):
            continue

        video_path = os.path.join(dir_path, "video.mp4")
        info_path = os.path.join(dir_path, "info.json")

        if not os.path.exists(video_path):
            continue

        try:
            # 根据视频时长自适应帧间隔，确保不超过 max_frames_per_video
            duration = _get_video_info(video_path)["duration"]
            if duration > 0:
                frame_interval = max(3, int(duration / max_frames_per_video))
            else:
                frame_interval = 5

            analysis = analyze_video(video_path, info_path, frame_interval=frame_interval)
            analysis["dir_name"] = dir_name
            results.append(analysis)
        except Exception as e:
            logger.error(f"分析失败 {dir_name}: {e}")

    # 按点赞数排序
    results.sort(key=lambda x: x.get("meta", {}).get("digg_count", 0), reverse=True)
    return results


# ==================== HTML 报告生成 ====================

def _fmt_time(seconds):
    """格式化秒数为 m:ss"""
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _fmt_num(n):
    """格式化数字"""
    if n >= 10000:
        return f"{n/10000:.1f}万"
    return str(n)


def generate_html_report(analyses, output_path, user_name="用户"):
    """
    生成可视化 HTML 分析报告

    Args:
        analyses: analyze_user_videos 的返回结果
        output_path: 输出 HTML 文件路径
        user_name: 用户名称
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 汇总统计
    video_analyses = [a for a in analyses if a["video_info"]["duration"] > 0]
    total_likes = sum(a.get("meta", {}).get("digg_count", 0) for a in video_analyses)
    total_comments = sum(a.get("meta", {}).get("comment_count", 0) for a in video_analyses)
    total_shots = sum(a["total_shots"] for a in video_analyses)
    total_duration = sum(a["video_info"]["duration"] for a in video_analyses)
    total_frames = sum(a.get("frame_stats", {}).get("total_frames", 0) for a in video_analyses)
    total_keyframes = sum(a.get("frame_stats", {}).get("keyframes", 0) for a in video_analyses)
    avg_shot = sum(a["avg_shot_length"] for a in video_analyses) / len(video_analyses) if video_analyses else 0

    # 标签统计
    tag_counter = Counter()
    for a in video_analyses:
        for t in a.get("meta", {}).get("topics", []):
            tag_counter[t] += 1

    # 生成 HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vlog 逐帧分析报告 - {user_name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.6; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
h1 {{ font-size: 28px; color: #58a6ff; margin-bottom: 8px; }}
h2 {{ font-size: 22px; color: #f0883e; margin: 30px 0 16px; padding-bottom: 8px; border-bottom: 2px solid #30363d; }}
h3 {{ font-size: 17px; color: #e6edf3; margin: 12px 0 8px; }}
.subtitle {{ color: #8b949e; font-size: 14px; margin-bottom: 24px; }}

/* 概览卡片 */
.overview {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 30px; }}
.overview-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; text-align: center; }}
.overview-card .value {{ font-size: 28px; font-weight: 700; color: #58a6ff; }}
.overview-card .label {{ font-size: 12px; color: #8b949e; margin-top: 4px; }}

/* 排名表 */
.rank-table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 13px; }}
.rank-table th {{ background: #161b22; color: #8b949e; padding: 10px 12px; text-align: left; border-bottom: 1px solid #30363d; font-weight: 600; }}
.rank-table td {{ padding: 10px 12px; border-bottom: 1px solid #21262d; }}
.rank-table tr:hover td {{ background: #1c2128; }}
.rank-table .rank-1 {{ color: #ffd700; font-weight: 700; }}
.rank-table .rank-2 {{ color: #c0c0c0; font-weight: 700; }}
.rank-table .rank-3 {{ color: #cd7f32; font-weight: 700; }}
.rank-table .num {{ text-align: right; font-variant-numeric: tabular-nums; }}

/* 视频详情卡片 */
.video-detail {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; margin-bottom: 24px; overflow: hidden; }}
.video-detail-header {{ padding: 16px 20px; background: #1c2128; border-bottom: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }}
.video-detail-header .title {{ font-size: 16px; font-weight: 600; color: #e6edf3; flex: 1; min-width: 200px; }}
.video-detail-header .stats {{ display: flex; gap: 16px; font-size: 13px; color: #8b949e; }}
.video-detail-header .stats span {{ white-space: nowrap; }}
.video-detail-body {{ padding: 16px 20px; }}

/* 节奏条形图 */
.rhythm-chart {{ display: flex; gap: 4px; align-items: flex-end; height: 120px; margin: 12px 0; }}
.rhythm-bar {{ flex: 1; background: linear-gradient(180deg, #58a6ff, #1f6feb); border-radius: 3px 3px 0 0; position: relative; min-width: 20px; }}
.rhythm-bar .bar-label {{ position: absolute; bottom: -22px; left: 50%; transform: translateX(-50%); font-size: 10px; color: #8b949e; white-space: nowrap; }}
.rhythm-bar .bar-value {{ position: absolute; top: -18px; left: 50%; transform: translateX(-50%); font-size: 10px; color: #58a6ff; white-space: nowrap; }}

/* 时间线 */
.timeline {{ position: relative; padding: 10px 0; margin: 12px 0; }}
.timeline-track {{ height: 6px; background: #21262d; border-radius: 3px; position: relative; }}
.timeline-marker {{ position: absolute; top: -4px; width: 3px; height: 14px; background: #f0883e; border-radius: 1px; }}
.timeline-labels {{ display: flex; justify-content: space-between; font-size: 10px; color: #8b949e; margin-top: 4px; }}

/* 帧网格 */
.frame-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 6px; margin: 12px 0; }}
.frame-grid img {{ width: 100%; border-radius: 4px; border: 1px solid #30363d; }}
.frame-grid .frame-time {{ font-size: 10px; color: #8b949e; text-align: center; margin-top: 2px; }}

/* 接触印片 */
img.contact-sheet {{ width: 100%; border-radius: 6px; border: 1px solid #30363d; margin: 8px 0; display: block; }}

/* 标签云 */
.tag-cloud {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }}
.tag {{ padding: 4px 12px; background: #1c2128; border: 1px solid #30363d; border-radius: 20px; font-size: 13px; color: #58a6ff; }}
.tag.hot {{ background: #1f2a38; border-color: #58a6ff; font-weight: 600; }}

/* 结构分段 */
.structure {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin: 12px 0; }}
.structure-seg {{ background: #1c2128; border: 1px solid #30363d; border-radius: 6px; padding: 12px; }}
.structure-seg .seg-name {{ font-size: 13px; font-weight: 600; color: #58a6ff; }}
.structure-seg .seg-time {{ font-size: 11px; color: #8b949e; }}
.structure-seg .seg-shots {{ font-size: 20px; font-weight: 700; color: #e6edf3; margin: 4px 0; }}
.structure-seg .seg-avg {{ font-size: 11px; color: #8b949e; }}

/* 对比面板 */
.compare-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin: 12px 0; }}
.compare-card {{ background: #1c2128; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }}
.compare-card .c-title {{ font-size: 14px; font-weight: 600; color: #e6edf3; margin-bottom: 8px; max-height: 40px; overflow: hidden; }}
.compare-card .c-metric {{ display: flex; justify-content: space-between; padding: 4px 0; font-size: 12px; border-bottom: 1px solid #21262d; }}
.compare-card .c-metric .c-label {{ color: #8b949e; }}
.compare-card .c-metric .c-value {{ color: #e6edf3; font-weight: 600; }}

/* 响应式 */
@media (max-width: 768px) {{
    .overview {{ grid-template-columns: repeat(2, 1fr); }}
    .frame-grid {{ grid-template-columns: repeat(3, 1fr); }}
}}
</style>
</head>
<body>
<div class="container">
<h1> Vlog 逐帧分析报告</h1>
<p class="subtitle">用户: {user_name} | 分析时间: {datetime.now().strftime("%Y-%m-%d %H:%M")} | 共 {len(video_analyses)} 个视频</p>

<!-- 概览 -->
<h2> 数据概览</h2>
<div class="overview">
<div class="overview-card"><div class="value">{len(video_analyses)}</div><div class="label">作品总数</div></div>
<div class="overview-card"><div class="value">{_fmt_num(total_likes)}</div><div class="label">总点赞</div></div>
<div class="overview-card"><div class="value">{_fmt_num(total_comments)}</div><div class="label">总评论</div></div>
<div class="overview-card"><div class="value">{round(total_duration/60)}分</div><div class="label">总时长</div></div>
<div class="overview-card"><div class="value">{total_shots}</div><div class="label">总镜头数</div></div>
<div class="overview-card"><div class="value">{avg_shot:.1f}秒</div><div class="label">平均镜头</div></div>
<div class="overview-card"><div class="value">{_fmt_num(total_frames)}</div><div class="label">总帧数</div></div>
<div class="overview-card"><div class="value">{_fmt_num(total_keyframes)}</div><div class="label">关键帧</div></div>
</div>

<!-- 爆款排名 -->
<h2> 爆款排名</h2>
<table class="rank-table">
<thead><tr><th>#</th><th>标题</th><th class="num">点赞</th><th class="num">评论</th><th class="num">收藏</th><th class="num">分享</th><th class="num">时长</th><th class="num">镜头</th><th class="num">平均镜头</th></tr></thead>
<tbody>
"""

    for i, a in enumerate(video_analyses[:20]):
        m = a.get("meta", {})
        rank_class = ""
        if i == 0:
            rank_class = "rank-1"
        elif i == 1:
            rank_class = "rank-2"
        elif i == 2:
            rank_class = "rank-3"
        title = m.get("title", a.get("dir_name", ""))[:50]
        html += f"""<tr>
<td class="{rank_class}">{i+1}</td>
<td>{title}</td>
<td class="num">{_fmt_num(m.get("digg_count", 0))}</td>
<td class="num">{_fmt_num(m.get("comment_count", 0))}</td>
<td class="num">{_fmt_num(m.get("collect_count", 0))}</td>
<td class="num">{_fmt_num(m.get("share_count", 0))}</td>
<td class="num">{_fmt_time(a["video_info"]["duration"])}</td>
<td class="num">{a["total_shots"]}</td>
<td class="num">{a["avg_shot_length"]}s</td>
</tr>
"""

    html += """</tbody></table>

<!-- 标签云 -->
<h2> 标签分析</h2>
<div class="tag-cloud">
"""

    for tag, count in tag_counter.most_common(20):
        hot = " hot" if count >= len(video_analyses) * 0.2 else ""
        html += f'<span class="tag{hot}">#{tag} ({count})</span>\n'

    html += """</div>
"""

    # TOP 3 对比
    if len(video_analyses) >= 3:
        html += """<h2> TOP 3 横向对比</h2>
<div class="compare-grid">
"""
        for i, a in enumerate(video_analyses[:3]):
            v = a["video_info"]
            r = a["rhythm"]
            m = a.get("meta", {})
            html += f"""<div class="compare-card">
<div class="c-title">TOP {i+1}: {m.get('title', '')[:40]}</div>
<div class="c-metric"><span class="c-label">时长</span><span class="c-value">{_fmt_time(v['duration'])}</span></div>
<div class="c-metric"><span class="c-label">分辨率</span><span class="c-value">{v['width']}×{v['height']}</span></div>
<div class="c-metric"><span class="c-label">总镜头</span><span class="c-value">{a['total_shots']} 个</span></div>
<div class="c-metric"><span class="c-label">平均镜头</span><span class="c-value">{a['avg_shot_length']} 秒</span></div>
<div class="c-metric"><span class="c-label">前10秒镜头</span><span class="c-value">{r.get('前10秒', {}).get('shots', '-')} 个</span></div>
<div class="c-metric"><span class="c-label">开场节奏</span><span class="c-value">{r.get('开场 (0-10%)', {}).get('avg_shot_length', '-')} 秒/镜头</span></div>
<div class="c-metric"><span class="c-label">高潮节奏</span><span class="c-value">{r.get('高潮 (33-66%)', {}).get('avg_shot_length', '-')} 秒/镜头</span></div>
<div class="c-metric"><span class="c-label">点赞</span><span class="c-value">{_fmt_num(m.get('digg_count', 0))}</span></div>
<div class="c-metric"><span class="c-label">标签</span><span class="c-value">{' '.join('#'+t for t in m.get('topics', [])[:5])}</span></div>
</div>
"""
        html += "</div>\n"

    # 逐视频详情
    html += "<h2> 逐视频详细分析</h2>\n"

    for i, a in enumerate(video_analyses):
        v = a["video_info"]
        m = a.get("meta", {})
        r = a["rhythm"]
        title = m.get("title", a.get("dir_name", "未知"))[:60]
        duration = v["duration"]

        html += f"""<div class="video-detail">
<div class="video-detail-header">
<div class="title">#{i+1} {title}</div>
<div class="stats">
<span> {_fmt_num(m.get('digg_count', 0))} 赞</span>
<span> {_fmt_num(m.get('comment_count', 0))} 评</span>
<span> {_fmt_time(duration)}</span>
<span> {a['total_shots']} 镜头</span>
</div>
</div>
<div class="video-detail-body">
"""

        # 节奏图
        html += '<h3> 节奏分析</h3>\n<div class="rhythm-chart">\n'
        max_avg = max((seg["avg_shot_length"] for seg in r.values()), default=1)
        rhythm_order = ["前10秒", "开场 (0-10%)", "叙事 (10-33%)", "高潮 (33-66%)", "收尾 (66-100%)", "全片"]
        for key in rhythm_order:
            if key in r:
                seg = r[key]
                height = max(5, int(seg["avg_shot_length"] / max(max_avg, 1) * 100))
                html += f'<div class="rhythm-bar" style="height:{height}px" title="{key}: {seg["avg_shot_length"]}秒/镜头"><div class="bar-value">{seg["avg_shot_length"]}s</div><div class="bar-label">{key.split("(")[0]}</div></div>\n'
        html += "</div>\n"

        # 结构分段
        html += '<div class="structure">\n'
        for key in rhythm_order:
            if key in r and key != "全片":
                seg = r[key]
                html += f"""<div class="structure-seg">
<div class="seg-name">{key}</div>
<div class="seg-time">{seg['start']}s - {seg['end']}s</div>
<div class="seg-shots">{seg['shots']} 镜头</div>
<div class="seg-avg">{seg['avg_shot_length']} 秒/镜头</div>
</div>
"""
        html += "</div>\n"

        # 镜头切换时间线
        if a["cuts"]:
            html += '<h3> 镜头切换时间线</h3>\n'
            html += '<div class="timeline"><div class="timeline-track">\n'
            for cut in a["cuts"]:
                pct = cut / duration * 100
                html += f'<div class="timeline-marker" style="left:{pct}%" title="{cut:.1f}s"></div>\n'
            html += '</div>\n<div class="timeline-labels">'
            for tick in range(0, int(duration) + 1, max(1, int(duration) // 8)):
                html += f"<span>{_fmt_time(tick)}</span>"
            html += "</div></div>\n"

        # 接触印片
        if a.get("contact_sheet_b64"):
            html += '<h3> 接触印片 (每{}秒一帧)</h3>\n'.format(a["frame_interval"])
            html += f'<img class="contact-sheet" src="data:image/jpeg;base64,{a["contact_sheet_b64"]}">\n'

        html += "</div></div>\n"

    html += """
</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"报告已生成: {output_path}")
    return output_path