"""采集路由。"""
from fastapi import APIRouter

from webapp.backend import deps
from webapp.backend.routers._common import active_auth
from webapp.backend.services import crawl as svc

router = APIRouter(prefix="/crawl", tags=["crawl"])


@router.get("/work")
async def work(url: str):
    return await svc.work_info(active_auth(), url)


@router.get("/user-info")
async def user_info(user_url: str):
    return await svc.user_info(active_auth(), user_url)


@router.post("/user-works")
async def user_works(body: dict):
    """提交为任务(可能很慢)。"""
    auth = active_auth()
    worker = svc.user_all_work(auth, body["user_url"],
                               body.get("save_choice", "all"), body.get("excel_name", ""))
    task_id = deps.get_task_manager().submit(
        "crawl.user_works", worker,
        params={"user_url": body["user_url"], "save_choice": body.get("save_choice", "all")})
    return {"task_id": task_id}


@router.get("/comments")
async def comments(url: str):
    auth = active_auth()
    worker = svc.all_comments(auth, url)
    task_id = deps.get_task_manager().submit("crawl.comments", worker, params={"url": url})
    return {"task_id": task_id}


@router.get("/followers")
async def followers(user_id: str, sec_id: str, num: int = 20):
    auth = active_auth()
    worker = svc.followers(auth, user_id, sec_id, num)
    task_id = deps.get_task_manager().submit("crawl.followers", worker,
                                              params={"user_id": user_id, "num": num})
    return {"task_id": task_id}


@router.get("/following")
async def following(user_id: str, sec_id: str, num: int = 20):
    auth = active_auth()
    worker = svc.following(auth, user_id, sec_id, num)
    task_id = deps.get_task_manager().submit("crawl.following", worker,
                                              params={"user_id": user_id, "num": num})
    return {"task_id": task_id}


@router.get("/favorites")
async def favorites(sec_id: str, max_cursor: str = "0", num: str = "18"):
    return await svc.favorites(active_auth(), sec_id, max_cursor, num)


@router.get("/notices")
async def notices(num: int = 20):
    return await svc.notices(active_auth(), num)


@router.get("/feed")
async def feed(count: str = "20"):
    return await svc.feed(active_auth(), count)


@router.get("/collect-list")
async def collect_list():
    return await svc.collect_list(active_auth())


@router.get("/rank")
async def rank(room_id: str, anchor_id: str, sec_anchor_id: str):
    return await svc.rank(active_auth(), room_id, anchor_id, sec_anchor_id)
