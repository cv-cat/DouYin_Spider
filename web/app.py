from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.config import WebConfig
from web.db import connect_db, init_db
from web.routes.pages import router as pages_router
from web.services.session_service import SessionService
from web.services.settings_service import SettingsService


def create_app(overrides=None) -> FastAPI:
    config = WebConfig(overrides)
    app = FastAPI(title="DouYin_Spider Web UI")
    with connect_db(config.db_path) as conn:
        init_db(conn)
    app.state.config = config
    app.state.settings_service = SettingsService(config.db_path)
    app.state.session_service = SessionService(config.db_path)
    app.mount("/static", StaticFiles(directory="web/static"), name="static")
    app.include_router(pages_router)
    return app
