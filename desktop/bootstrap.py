from dataclasses import dataclass
import os
import sys

from web.config import WebConfig
from web.db import connect_db, init_db
from web.services.agent_acquisition_service import AgentAcquisitionService
from web.services.crawl_service import CrawlService
from web.services.im_service import IMService
from web.services.lead_scoring_service import LeadScoringService
from web.services.live_service import LiveService
from web.services.login_service import LoginService
from web.services.session_service import SessionService
from web.tasks.broker import EventBroker
from web.tasks.manager import TaskManager


@dataclass(frozen=True)
class DesktopServices:
    app: object | None
    config: object
    agent: object
    session: object
    live: object
    im: object
    task_manager: object
    broker: object | None = None
    login: object | None = None

    @property
    def login_service(self):
        return self.login

    @property
    def session_service(self):
        return self.session

    @property
    def live_service(self):
        return self.live

    @property
    def im_service(self):
        return self.im


def build_services(overrides=None):
    overrides = overrides or {}
    config = WebConfig(overrides)
    _configure_proxy_behavior(config)
    _configure_playwright_behavior(config)

    with connect_db(config.db_path) as conn:
        init_db(conn)

    broker = EventBroker()
    task_manager = TaskManager(config.db_path, broker=broker)
    session = SessionService(config.db_path)
    crawl = CrawlService(config, session, task_manager)
    live = LiveService(config.db_path, session, task_manager, broker)
    im = IMService(config.db_path, session, task_manager, broker)
    login = LoginService(config.db_path, task_manager, broker)
    scoring = LeadScoringService()
    agent = AgentAcquisitionService(
        config.db_path,
        config.project_root / "datas" / "runtime",
        task_manager,
        crawl,
        scoring,
        im,
        live,
    )

    return DesktopServices(
        app=None,
        config=config,
        agent=agent,
        session=session,
        live=live,
        im=im,
        task_manager=task_manager,
        broker=broker,
        login=login,
    )


def _configure_proxy_behavior(config: WebConfig):
    if config.use_system_proxy:
        return
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


def _configure_playwright_behavior(config: WebConfig):
    if getattr(sys, "frozen", False):
        _setup_frozen_runtime()
        return
    local_browser_dir = config.project_root / ".playwright"
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ and local_browser_dir.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(local_browser_dir)


def _frozen_browsers_dir():
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/liangbashuazi")
    elif sys.platform == "win32":
        base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "liangbashuazi")
    else:
        base = os.path.expanduser("~/.liangbashuazi")
    return os.path.join(base, "ms-playwright")


def _setup_frozen_runtime():
    # 1) execjs 复用 playwright 自带 node（用户免装 Node.js）
    try:
        from playwright._impl._driver import compute_driver_executable
        node_path = compute_driver_executable()[0]
        node_dir = os.path.dirname(node_path)
        os.environ["PATH"] = node_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass
    # 2) chromium 放用户可写目录（首次运行下载到这）
    browsers = _frozen_browsers_dir()
    try:
        os.makedirs(browsers, exist_ok=True)
    except Exception:
        pass
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers  # 打包版强制用用户目录（首次下载到这）


def ensure_chromium():
    """检测 chromium，缺则用 playwright 自带 driver 下载。返回 (ok, message)。
    开发环境(.playwright 已有 chromium)会直接返回 True，不下载。"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
            if exe and os.path.exists(exe):
                return True, "浏览器已就绪"
    except Exception:
        pass
    try:
        import subprocess
        from playwright._impl._driver import compute_driver_executable, get_driver_env
        drv = compute_driver_executable()
        env = get_driver_env()
        if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
            env["PLAYWRIGHT_BROWSERS_PATH"] = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
        result = subprocess.run(
            [*drv, "install", "chromium"], env=env, capture_output=True, text=True
        )
        if result.returncode == 0:
            return True, "浏览器下载完成"
        return False, (result.stderr or result.stdout or "")[-300:]
    except Exception as exc:
        return False, str(exc)
