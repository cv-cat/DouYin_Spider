"""下载路由:浏览/下载采集产物。"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from webapp.backend import config
from webapp.backend.models.schemas import FileNode

router = APIRouter(prefix="/downloads", tags=["downloads"])


def _safe_join(base: str, rel: str) -> str:
    base_abs = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base_abs, rel))
    if not target.startswith(base_abs + os.sep) and target != base_abs:
        raise HTTPException(400, "非法路径")
    return target


def _build_tree(path: str, name: str, depth: int = 0, max_depth: int = 3) -> FileNode:
    is_dir = os.path.isdir(path)
    node = FileNode(name=name, path=os.path.relpath(path, config.DATA_DIR), is_dir=is_dir)
    if is_dir:
        if depth < max_depth:
            for entry in sorted(os.listdir(path)):
                p = os.path.join(path, entry)
                node.children.append(_build_tree(p, entry, depth + 1, max_depth))
    else:
        node.size = os.path.getsize(path)
    return node


@router.get("/tree", response_model=FileNode)
async def tree():
    return _build_tree(config.DATA_DIR, "datas")


@router.get("/file")
async def file(path: str):
    full = _safe_join(config.DATA_DIR, path)
    if not os.path.isfile(full):
        raise HTTPException(404, "文件不存在")
    return FileResponse(full, filename=os.path.basename(full))
