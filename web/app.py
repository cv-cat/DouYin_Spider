from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.config import WebConfig
from web.db import connect_db, init_db
from web.routes.actions import router as actions_router
from web.routes.pages import router as pages_router
from web.routes.streams import router as streams_router
from web.services.crawl_service import CrawlService
from web.services.acquisition_dashboard_service import AcquisitionDashboardService
from web.services.im_service import IMService
from web.services.keyword_funnel_service import KeywordFunnelService
from web.services.live_service import LiveService
from web.services.lead_scoring_service import LeadScoringService
from web.services.login_service import LoginService
from web.services.outreach_service import OutreachService
from web.services.rules_service import RulesService
from web.services.session_service import SessionService
from web.services.settings_service import SettingsService
from web.tasks.broker import EventBroker
from web.tasks.manager import TaskManager


def create_app(overrides=None) -> FastAPI:
    config = WebConfig(overrides)
    app = FastAPI(title="DouYin_Spider Web UI", debug=True)
    with connect_db(config.db_path) as conn:
        init_db(conn)
    app.state.config = config
    app.state.broker = EventBroker()
    app.state.task_manager = TaskManager(config.db_path, broker=app.state.broker)
    app.state.settings_service = SettingsService(config.db_path)
    app.state.session_service = SessionService(config.db_path)
    app.state.crawl_service = CrawlService(config, app.state.session_service, app.state.task_manager)
    app.state.live_service = LiveService(config.db_path, app.state.session_service, app.state.task_manager, app.state.broker)
    app.state.im_service = IMService(config.db_path, app.state.session_service, app.state.task_manager, app.state.broker)
    app.state.lead_scoring_service = LeadScoringService()
    app.state.keyword_funnel_service = KeywordFunnelService(
        config.db_path,
        app.state.task_manager,
        app.state.crawl_service,
        app.state.im_service,
        app.state.lead_scoring_service,
    )
    app.state.acquisition_dashboard_service = AcquisitionDashboardService(config.db_path)
    app.state.outreach_service = OutreachService(config.db_path)
    app.state.rules_service = RulesService(config.db_path)
    app.state.login_service = LoginService(config.db_path, app.state.task_manager, app.state.broker)
    app.state.templates = Jinja2Templates(directory=str(config.templates_dir))
    app.mount("/static", StaticFiles(directory=str(config.static_dir)), name="static")
    app.include_router(pages_router)
    app.include_router(streams_router)
    app.include_router(actions_router)
    return app
