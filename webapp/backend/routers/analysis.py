"""视频逐帧分析路由。"""
import os
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from webapp.backend import config
from webapp.backend.models.schemas import Ok

router = APIRouter(prefix="/analysis", tags=["analysis"])

# 分析任务状态(内存)
_analysis_jobs: dict[str, dict] = {}

# 报告输出目录
REPORTS_DIR = os.path.join(config.DATA_DIR, "analysis_reports")


def _ensure_reports_dir():
    os.makedirs(REPORTS_DIR, exist_ok=True)


def _list_user_dirs():
    """列出 datas/media_datas 下的用户目录"""
    dirs = []
    if os.path.isdir(config.MEDIA_DIR):
        for name in sorted(os.listdir(config.MEDIA_DIR)):
            full = os.path.join(config.MEDIA_DIR, name)
            if os.path.isdir(full) and not name.startswith("."):
                # 统计视频数
                video_count = 0
                for sub in os.listdir(full):
                    if os.path.isdir(os.path.join(full, sub)):
                        if os.path.exists(os.path.join(full, sub, "video.mp4")):
                            video_count += 1
                dirs.append({"name": name, "path": full, "video_count": video_count})
    return dirs


@router.get("/users")
async def list_users():
    """列出可分析的用户目录"""
    return _list_user_dirs()


@router.get("/reports")
async def list_reports():
    """列出已有分析报告"""
    _ensure_reports_dir()
    reports = []
    if os.path.isdir(REPORTS_DIR):
        for f in sorted(os.listdir(REPORTS_DIR), reverse=True):
            if f.endswith(".html"):
                fp = os.path.join(REPORTS_DIR, f)
                reports.append({
                    "filename": f,
                    "size": os.path.getsize(fp),
                    "modified": os.path.getmtime(fp),
                })
    return reports


@router.get("/report/{filename}")
async def get_report(filename: str):
    """获取报告 HTML 内容"""
    _ensure_reports_dir()
    fp = os.path.join(REPORTS_DIR, filename)
    if not os.path.isfile(fp) or not filename.endswith(".html"):
        raise HTTPException(404, "报告不存在")
    return HTMLResponse(content=open(fp, encoding="utf-8").read())


@router.get("/report/{filename}/download")
async def download_report(filename: str):
    """下载报告文件"""
    _ensure_reports_dir()
    fp = os.path.join(REPORTS_DIR, filename)
    if not os.path.isfile(fp) or not filename.endswith(".html"):
        raise HTTPException(404, "报告不存在")
    return FileResponse(fp, filename=filename, media_type="text/html")


@router.post("/run")
async def run_analysis(user_dir: str = "", max_frames: int = 20):
    """触发视频分析任务(同步执行,轮询结果)"""
    if not user_dir:
        raise HTTPException(400, "请指定用户目录")

    full_path = os.path.join(config.MEDIA_DIR, user_dir) if not os.path.isabs(user_dir) else user_dir
    if not os.path.isdir(full_path):
        raise HTTPException(400, f"目录不存在: {full_path}")

    _ensure_reports_dir()

    import uuid
    job_id = uuid.uuid4().hex[:12]
    _analysis_jobs[job_id] = {"status": "running", "progress": 0, "result": None, "error": None}

    def _run():
        try:
            from utils.video_analyzer import analyze_user_videos, generate_html_report
            _analysis_jobs[job_id]["progress"] = 0.1

            user_name = os.path.basename(full_path.rstrip("/"))
            if "_" in user_name:
                user_name = user_name.split("_")[0]

            analyses = analyze_user_videos(full_path, max_frames_per_video=max_frames)
            _analysis_jobs[job_id]["progress"] = 0.7

            if not analyses:
                _analysis_jobs[job_id]["status"] = "failed"
                _analysis_jobs[job_id]["error"] = "未找到可分析的视频"
                return

            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{user_name}_{timestamp}.html"
            output_path = os.path.join(REPORTS_DIR, filename)
            generate_html_report(analyses, output_path, user_name)

            video_count = sum(1 for a in analyses if a["video_info"]["duration"] > 0)
            total_likes = sum(a.get("meta", {}).get("digg_count", 0) for a in analyses)

            _analysis_jobs[job_id]["status"] = "done"
            _analysis_jobs[job_id]["progress"] = 1.0
            _analysis_jobs[job_id]["result"] = {
                "filename": filename,
                "video_count": video_count,
                "total_likes": total_likes,
                "report_url": f"/api/analysis/report/{filename}",
            }
        except Exception as e:
            _analysis_jobs[job_id]["status"] = "failed"
            _analysis_jobs[job_id]["error"] = str(e)

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    """查询分析任务状态"""
    job = _analysis_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return job