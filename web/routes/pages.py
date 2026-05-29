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
