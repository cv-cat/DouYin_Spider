"""互动路由:点赞/评论/收藏。"""
from fastapi import APIRouter

from webapp.backend.routers._common import active_auth
from webapp.backend.services import interact as svc

router = APIRouter(prefix="/interact", tags=["interact"])


@router.post("/digg")
async def digg(body: dict):
    return await svc.digg(active_auth(), body["aweme_id"], body.get("digg_type", "1"))


@router.post("/comment")
async def comment(body: dict):
    return await svc.comment(active_auth(), body["aweme_id"], body["content"], body.get("reply_id", ""))


@router.post("/collect")
async def collect(body: dict):
    return await svc.collect(active_auth(), body["aweme_id"], body.get("action", "1"))


@router.post("/collect/move")
async def collect_move(body: dict):
    return await svc.collect_move(active_auth(), body["aweme_id"], body["collect_name"], body["collect_id"])


@router.post("/collect/remove")
async def collect_remove(body: dict):
    return await svc.collect_remove(active_auth(), body["aweme_id"], body["collect_name"], body["collect_id"])
