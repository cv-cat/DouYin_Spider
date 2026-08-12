"""下载路由:浏览/下载采集产物。"""
import os
import tempfile
import urllib.parse
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from webapp.backend import config
from webapp.backend.models.schemas import FileNode

router = APIRouter(prefix="/downloads", tags=["downloads"])


def _safe_join(base: str, rel: str) -> str:
    base_abs = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base_abs, rel))
    if not target.startswith(base_abs + os.sep) and target != base_abs:
        raise HTTPException(400, "非法路径")
    return target


def _has_children(path: str) -> bool:
    try:
        return next(os.scandir(path), None) is not None
    except OSError:
        return False


def _list_children(full: str) -> list[FileNode]:
    nodes: list[FileNode] = []
    for entry in sorted(os.listdir(full)):
        p = os.path.join(full, entry)
        is_dir = os.path.isdir(p)
        nodes.append(
            FileNode(
                name=entry,
                path=os.path.relpath(p, config.DATA_DIR),
                is_dir=is_dir,
                size=0 if is_dir else os.path.getsize(p),
                has_children=is_dir and _has_children(p),
            )
        )
    return nodes


@router.get("/children", response_model=list[FileNode])
async def children(path: str = ""):
    """返回某目录的直接子项(懒加载)。path 为空时返回根级。"""
    full = _safe_join(config.DATA_DIR, path) if path else config.DATA_DIR
    if not os.path.isdir(full):
        raise HTTPException(404, "目录不存在")
    return _list_children(full)


@router.get("/file")
async def file(path: str):
    full = _safe_join(config.DATA_DIR, path)
    if not os.path.isfile(full):
        raise HTTPException(404, "文件不存在")
    return FileResponse(full, filename=os.path.basename(full))


@router.get("/dir")
async def download_dir(path: str):
    """把整个目录打包成 zip 流式下载。"""
    full = _safe_join(config.DATA_DIR, path)
    if not os.path.isdir(full):
        raise HTTPException(404, "目录不存在")

    root_name = os.path.basename(full.rstrip(os.sep)) or "datas"
    zip_name = root_name + ".zip"

    def gen():
        # 写入临时文件,支持大目录,避免撑爆内存
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        tmp_path = tmp.name
        tmp.close()
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for dirpath, _dirnames, filenames in os.walk(full):
                    for fn in filenames:
                        fp = os.path.join(dirpath, fn)
                        arc = os.path.join(root_name, os.path.relpath(fp, full))
                        zf.write(fp, arc)
            with open(tmp_path, "rb") as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    encoded = urllib.parse.quote(zip_name)
    ascii_fallback = zip_name.encode("ascii", "ignore").decode("ascii") or "download.zip"
    return StreamingResponse(
        gen(),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'
            )
        },
    )
