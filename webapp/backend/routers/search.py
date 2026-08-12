"""搜索路由。"""
from fastapi import APIRouter

from webapp.backend import deps
from webapp.backend.routers._common import active_auth
from webapp.backend.services import search as svc

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/work")
async def search_work(body: dict):
    auth = active_auth()
    worker = svc.works(
        auth, body["query"], body.get("num", 20),
        body.get("sort_type", "0"), body.get("publish_time", "0"),
        body.get("filter_duration", ""), body.get("search_range", "0"),
        body.get("content_type", "0"),
        body.get("save_choice", ""), body.get("excel_name", ""),
    )
    task_id = deps.get_task_manager().submit(
        "search.work", worker,
        params={"query": body["query"], "num": body.get("num", 20)})
    return {"task_id": task_id}


@router.post("/user")
async def search_user(body: dict):
    return await svc.users(active_auth(), body["query"], body.get("num", 20))


@router.post("/live")
async def search_live(body: dict):
    return await svc.lives(active_auth(), body["query"], body.get("num", 20))
