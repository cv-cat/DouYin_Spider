"""FastAPI 应用入口。

开发:uvicorn webapp.backend.main:app --reload --port 8000
生产:先 cd webapp/frontend && npm run build,再启动本应用(自动托管 dist)
"""
import os
import sys

# 把仓库根目录加入 sys.path,使 SDK(dy_apis/builder/utils/static)可被导入
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from webapp.backend import config, deps
from webapp.backend.routers import (
    accounts, crawl, search, live, messages, interact, tasks, downloads, analysis,
)


def create_app() -> FastAPI:
    config.ensure_dirs()
    deps.init_deps()

    app = FastAPI(title="DouYin Spider Web", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 业务路由
    for r in (accounts, crawl, search, live, messages, interact, tasks, downloads, analysis):
        app.include_router(r.router, prefix=config.API_PREFIX)

    # 生产态:托管前端构建产物
    if os.path.isdir(config.FRONTEND_DIST):
        app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("webapp.backend.main:app", host="0.0.0.0", port=8000, reload=False)
