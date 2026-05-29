from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.db import connect_db
from web.toolbox_catalog import CRAWL_TOOL_GROUPS, LIVE_TOOL_GROUPS

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


@router.get("/keyword-funnel", response_class=HTMLResponse)
def keyword_funnel_page(request: Request):
    selected_run_id = request.query_params.get("run_id", "")
    partial = request.query_params.get("partial")
    service = request.app.state.keyword_funnel_service
    defaults = request.app.state.rules_service.defaults()
    runs = service.list_runs()
    leads = service.list_leads(selected_run_id)
    if partial == "runs":
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="components/keyword_run_table.html",
            context={"runs": runs, "selected_run_id": selected_run_id},
        )
    if partial == "leads":
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="components/keyword_lead_table.html",
            context={"leads": leads, "selected_run_id": selected_run_id},
        )
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="keyword_funnel.html",
        context={
            "title": "关键词截流",
            "runs": runs,
            "leads": leads,
            "selected_run_id": selected_run_id,
            "defaults": defaults,
        },
    )


@router.get("/acquisition-dashboard", response_class=HTMLResponse)
def acquisition_dashboard_page(request: Request):
    summary = request.app.state.acquisition_dashboard_service.summary()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="acquisition_dashboard.html",
        context={"title": "获客仪表盘", "summary": summary},
    )


@router.get("/lead-pool", response_class=HTMLResponse)
def lead_pool_page(request: Request):
    filters = {
        "grade": request.query_params.get("grade", ""),
        "source_type": request.query_params.get("source_type", ""),
        "review_status": request.query_params.get("review_status", ""),
        "message_status": request.query_params.get("message_status", ""),
    }
    leads = request.app.state.keyword_funnel_service.list_leads(**filters)
    if request.query_params.get("partial") == "table":
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="components/lead_pool_table.html",
            context={"leads": leads},
        )
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="lead_pool.html",
        context={"title": "线索池", "leads": leads, "filters": filters},
    )


@router.get("/outreach-center", response_class=HTMLResponse)
def outreach_center_page(request: Request):
    service = request.app.state.outreach_service
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="outreach_center.html",
        context={
            "title": "触达中心",
            "modes": service.list_modes(),
            "templates": service.list_templates(),
            "queue": service.queue_preview(),
        },
    )


@router.get("/conversion-tracking", response_class=HTMLResponse)
def conversion_tracking_page(request: Request):
    summary = request.app.state.acquisition_dashboard_service.summary()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="conversion_tracking.html",
        context={"title": "转化跟踪", "summary": summary},
    )


@router.get("/rules-center", response_class=HTMLResponse)
def rules_center_page(request: Request):
    defaults = request.app.state.rules_service.defaults()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="rules_center.html",
        context={"title": "规则中心", "defaults": defaults},
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


@router.get("/api-tools", response_class=HTMLResponse)
def api_tools_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="api_tools.html",
        context={
            "title": "接口工具",
            "crawl_tool_groups": CRAWL_TOOL_GROUPS,
            "live_tool_groups": LIVE_TOOL_GROUPS,
        },
    )
