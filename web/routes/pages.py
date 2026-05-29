from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.db import connect_db

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def overview(request: Request):
    with connect_db(request.app.state.config.db_path) as conn:
        auth_row = conn.execute("select status from auth_sessions where scope = 'douyin'").fetchone()
        live_count = conn.execute("select count(*) as c from live_watchers where status = 'running'").fetchone()["c"]
        im_count = conn.execute("select count(*) as c from im_receivers where status = 'running'").fetchone()["c"]
        failed_count = conn.execute("select count(*) as c from tasks where status = 'failed'").fetchone()["c"]
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="overview.html",
        context={
            "title": "DouYin_Spider Web UI",
            "auth_status": auth_row["status"] if auth_row else "missing",
            "live_count": live_count,
            "im_count": im_count,
            "failed_count": failed_count,
            "host": request.app.state.config.host,
            "port": request.app.state.config.port,
        },
    )


@router.get("/login", response_class=HTMLResponse)
def login_center(request: Request):
    sessions = request.app.state.session_service
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "title": "登录中心",
            "douyin_auth": sessions.load_auth("douyin"),
        },
    )


@router.get("/data-crawl", response_class=HTMLResponse)
def data_crawl_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="data_crawl.html",
        context={"title": "数据抓取"},
    )


@router.get("/live-monitor", response_class=HTMLResponse)
def live_monitor_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="live_monitor.html",
        context={"title": "直播监听"},
    )


@router.get("/private-messages", response_class=HTMLResponse)
def private_messages_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="private_messages.html",
        context={"title": "私信中心"},
    )


@router.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request):
    partial = request.query_params.get("partial")
    with connect_db(request.app.state.config.db_path) as conn:
        rows = conn.execute("select * from tasks order by started_at desc").fetchall()
        tasks = []
        for row in rows:
            task = dict(row)
            log_row = conn.execute(
                "select message from task_logs where task_id = ? order by created_at desc limit 1",
                (task["task_id"],),
            ).fetchone()
            task["traceback"] = log_row["message"] if log_row else ""
            tasks.append(task)
    template_name = "components/task_rows.html" if partial == "rows" else "tasks.html"
    return request.app.state.templates.TemplateResponse(
        request=request,
        name=template_name,
        context={"title": "任务与日志", "tasks": tasks},
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    settings_data = {
        "media_dir": str(request.app.state.config.media_dir),
        "excel_dir": str(request.app.state.config.excel_dir),
        "port": request.app.state.config.port,
    }
    settings_data.update(request.app.state.settings_service.load())
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"title": "设置", "settings_data": settings_data},
    )
