from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.config import WebConfig
from web.routes.pages import router as pages_router


def create_app(overrides=None) -> FastAPI:
    config = WebConfig(overrides)
    app = FastAPI(title="DouYin_Spider Web UI")
    app.state.config = config
    app.mount("/static", StaticFiles(directory="web/static"), name="static")
    app.include_router(pages_router)
    return app
