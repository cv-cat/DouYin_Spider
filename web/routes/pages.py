from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/", response_class=HTMLResponse)
def overview(request: Request):
    settings_data = request.app.state.settings_service.load()
    return templates.TemplateResponse(
        request=request,
        name="overview.html",
        context={
            "title": "DouYin_Spider Web UI",
            "settings_data": settings_data,
        },
    )


@router.get("/login", response_class=HTMLResponse)
def login_center(request: Request):
    sessions = request.app.state.session_service
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "title": "登录中心",
            "douyin_auth": sessions.load_auth("douyin"),
        },
    )


@router.get("/data-crawl", response_class=HTMLResponse)
def data_crawl_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="data_crawl.html",
        context={"title": "数据抓取"},
    )
