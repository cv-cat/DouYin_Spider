import time

from web.services.login_service import LoginService
from web.services.crawl_service import VerificationRequiredError
from fastapi.testclient import TestClient

from web.app import create_app


def test_manual_cookie_save_updates_session(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)

    response = client.post(
        "/actions/login/cookies",
        data={"scope": "douyin", "cookie_str": "msToken=test; sessionid=abc"},
    )

    assert response.status_code == 200
    assert "manual cookie saved" in response.text


def test_finish_phone_login_uses_verification_code_api(tmp_path):
    class DummySessions:
        def load_auth(self, scope):
            return {"scope": scope}

        def save_cookie(self, scope, cookie_str, status):
            self.saved = (scope, cookie_str, status)

    class DummyTaskManager:
        def submit(self, task_type, summary, runner):
            return runner()

    class DummyBroker:
        def publish(self, channel, payload):
            return None

    class DummyAuth:
        cookie_str = "cookie=stale"
        cookie = {"sessionid": "updated", "msToken": "next"}

    class DummyApi:
        def dyPhoneVerificationCodeLogin(self, auth, phone_num, code):
            return {"status": "ok", "phone_num": phone_num, "code": code}, DummyAuth()

    service = LoginService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        DummyBroker(),
        api_cls=DummyApi,
    )
    service.sessions = DummySessions()

    result = service.finish_phone_login("13800000000", "123456")

    assert result["status"] == "ok"
    assert service.sessions.saved == ("douyin", "sessionid=updated; msToken=next", "phone-login-success")


def test_persist_login_record_uses_login_api(tmp_path):
    class DummySessions:
        def load_auth(self, scope):
            class DummyAuth:
                cookie_str = "cookie=ok"

            return DummyAuth()

        def save_cookie(self, scope, cookie_str, status):
            self.saved = (scope, cookie_str, status)

    class DummyTaskManager:
        def submit(self, task_type, summary, runner):
            return runner()

    class DummyBroker:
        def publish(self, channel, payload):
            return None

    class DummyApi:
        def persistenceLoginInfo(self, auth):
            return {"status": "persisted"}

    service = LoginService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        DummyBroker(),
        api_cls=DummyApi,
    )
    service.sessions = DummySessions()

    result = service.persist_login_record("douyin")

    assert result["status"] == "persisted"


def test_begin_qr_login_returns_qr_session_payload(tmp_path):
    class DummyTaskManager:
        def submit(self, task_type, summary, runner):
            return runner()

    class DummyBroker:
        def publish(self, channel, payload):
            return None

    class DummyAuth:
        cookie_str = "cookie=qr"
        cookie = {"sessionid": "qr-updated"}
        msToken = "token"
        cookie = {"sessionid": "qr-updated", "msToken": "token"}
        cookie = {"sessionid": "qr-updated", "msToken": "token"}

    class DummyApi:
        async def dyGenerateInitData(self, headless=True):
            return DummyAuth()

        def dyGenerateQRcode(self, auth):
            return {"data": {"token": "token-1", "qrcode_index_url": "https://example.com/qr-login"}}

    service = LoginService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        DummyBroker(),
        api_cls=DummyApi,
    )

    result = service.begin_qr_login()

    assert result["session_id"]
    assert result["status"] == "pending"
    assert result["verify_url"] == "https://example.com/qr-login"
    assert result["qr_image_data_url"].startswith("data:image/")


def test_poll_qr_login_success_saves_cookie(tmp_path):
    class DummySessions:
        def save_cookie(self, scope, cookie_str, status):
            self.saved = (scope, cookie_str, status)

    class DummyTaskManager:
        def submit(self, task_type, summary, runner):
            return runner()

    class DummyBroker:
        def publish(self, channel, payload):
            return None

    class DummyAuth:
        cookie_str = "cookie=qr"
        cookie = {"sessionid": "qr-updated"}
        msToken = "token"

    class DummyApi:
        async def dyGenerateInitData(self, headless=True):
            return DummyAuth()

        def dyGenerateQRcode(self, auth):
            assert auth.cookie["msToken"] == "token"
            return {"data": {"token": "token-1", "qrcode_index_url": "https://example.com/qr-login"}}

        def dyCheckQrCodeLogin(self, auth, token):
            return {"data": {"status": "3"}}

    service = LoginService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        DummyBroker(),
        api_cls=DummyApi,
    )
    service.sessions = DummySessions()
    session = service.begin_qr_login()

    result = service.poll_qr_login(session["session_id"])

    assert result["status"] == "3"
    assert result["done"] is True
    assert service.sessions.saved == ("douyin", "sessionid=qr-updated; msToken=token", "qr-success")


def test_request_phone_code_returns_captcha_payload_without_blocking(tmp_path):
    class DummySessions:
        def save_cookie(self, scope, cookie_str, status):
            self.saved = (scope, cookie_str, status)

    class DummyTaskManager:
        def submit(self, task_type, summary, runner):
            return runner()

    class DummyBroker:
        def publish(self, channel, payload):
            return None

    class DummyAuth:
        cookie_str = "cookie=phone"
        cookie = {"sessionid": "bootstrap"}
        msToken = "token"

    class DummyApi:
        async def dyGenerateInitData(self, headless=True):
            return DummyAuth()

        def dyGeneratePhoneVerificationCode(self, phone_num, auth, interactive=True):
            assert auth.cookie["msToken"] == "token"
            return {
                "status": "captcha_required",
                "iframe_html": "<iframe src='https://verify.example'></iframe>",
            }

    service = LoginService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        DummyBroker(),
        api_cls=DummyApi,
    )
    service.sessions = DummySessions()

    result = service.request_phone_code("13800000000")

    assert result["status"] == "captcha_required"
    assert "iframe" in result["iframe_html"]
    assert "13800000000" in service.pending_phone_requests
    assert service.sessions.saved == ("douyin", "sessionid=bootstrap; msToken=token", "phone-code-bootstrap")


def test_request_phone_code_retries_with_pending_auth_after_slider(tmp_path):
    class DummySessions:
        def save_cookie(self, scope, cookie_str, status):
            self.saved = (scope, cookie_str, status)

    class DummyTaskManager:
        def submit(self, task_type, summary, runner):
            return runner()

    class DummyBroker:
        def publish(self, channel, payload):
            return None

    class DummyAuth:
        cookie_str = "cookie=phone"
        cookie = {"sessionid": "bootstrap"}
        msToken = "token"

    class DummyApi:
        async def dyGenerateInitData(self, headless=True):
            return DummyAuth()

        def dyGeneratePhoneVerificationCode(self, phone_num, auth, interactive=True):
            assert auth.cookie["msToken"] == "token"
            return {
                "status": "captcha_required",
                "iframe_html": "<iframe src='https://verify.example'></iframe>",
            }

        def retryPhoneVerificationCode(self, phone_num, auth):
            return {"status": "sent"}

    service = LoginService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        DummyBroker(),
        api_cls=DummyApi,
    )
    service.sessions = DummySessions()
    service.request_phone_code("13800000000")

    result = service.request_phone_code("13800000000")

    assert result["status"] == "sent"
    assert service.pending_phone_requests == {}
    assert service.sessions.saved == ("douyin", "sessionid=bootstrap; msToken=token", "phone-code-requested")


def test_qr_login_action_renders_qr_panel(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyLoginService:
        def begin_qr_login(self):
            return {
                "session_id": "qr-1",
                "status": "pending",
                "verify_url": "https://example.com/qr-login",
                "qr_image_data_url": "data:image/png;base64,abc",
            }

    app.state.login_service = DummyLoginService()
    client = TestClient(app)

    response = client.post("/actions/login/qr")

    assert response.status_code == 200
    assert "扫码状态" in response.text
    assert "data:image/png;base64,abc" in response.text


def test_phone_request_action_renders_slider_iframe(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyLoginService:
        def request_phone_code(self, phone_num):
            return {
                "status": "captcha_required",
                "iframe_html": "<iframe src='https://verify.example'></iframe>",
            }

    app.state.login_service = DummyLoginService()
    client = TestClient(app)

    response = client.post("/actions/login/phone/request-code", data={"phone_num": "13800000000"})

    assert response.status_code == 200
    assert "verify.example" in response.text


def test_begin_browser_login_auto_saves_douyin_and_live_cookies(tmp_path):
    class DummySessions:
        def __init__(self):
            self.saved = []

        def save_cookie(self, scope, cookie_str, status):
            self.saved.append((scope, cookie_str, status))

    class DummyTaskManager:
        def submit(self, task_type, summary, runner):
            return runner()

    class DummyBroker:
        def publish(self, channel, payload):
            return None

    def fake_browser_runner(session_id, update_state):
        update_state(session_id, "waiting", False, "浏览器已打开，请完成登录")
        return {
            "douyin": "sessionid=abc; msToken=token-1",
            "live": "sessionid=abc; webcast=1; msToken=token-1",
        }

    service = LoginService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        DummyBroker(),
        browser_login_runner=fake_browser_runner,
    )
    service.sessions = DummySessions()

    started = service.begin_browser_login()

    deadline = time.time() + 2
    state = started
    while time.time() < deadline:
        state = service.poll_browser_login(started["session_id"])
        if state["done"]:
            break
        time.sleep(0.05)

    assert state["status"] == "success"
    assert state["done"] is True
    assert service.sessions.saved == [
        ("douyin", "sessionid=abc; msToken=token-1", "browser-login-success"),
        ("live", "sessionid=abc; webcast=1; msToken=token-1", "browser-login-success"),
    ]


def test_login_page_prefills_saved_cookie_textareas(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)
    client.post("/actions/login/cookies", data={"scope": "douyin", "cookie_str": "sessionid=abc; msToken=token-1"})
    client.post("/actions/login/cookies", data={"scope": "live", "cookie_str": "sessionid=abc; webcast=1; msToken=token-1"})

    response = client.get("/login")

    assert response.status_code == 200
    assert "sessionid=abc; msToken=token-1" in response.text
    assert "sessionid=abc; webcast=1; msToken=token-1" in response.text
    assert "一键网页登录并自动保存 Cookie" in response.text


def test_browser_login_action_renders_status_panel(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyLoginService:
        def begin_browser_login(self):
            return {
                "session_id": "browser-1",
                "status": "launching",
                "done": False,
                "message": "正在打开网页登录窗口",
            }

    app.state.login_service = DummyLoginService()
    client = TestClient(app)

    response = client.post("/actions/login/browser")

    assert response.status_code == 200
    assert "网页登录状态" in response.text
    assert "browser-1" in response.text
    assert "正在打开网页登录窗口" in response.text


def test_browser_login_confirm_action_sets_pending_confirmation(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyLoginService:
        def confirm_browser_login(self, session_id):
            return {
                "session_id": session_id,
                "status": "saving",
                "done": False,
                "message": "已收到确认，正在保存 Cookie。",
            }

    app.state.login_service = DummyLoginService()
    client = TestClient(app)

    response = client.post("/actions/login/browser/confirm", data={"session_id": "browser-1"})

    assert response.status_code == 200
    assert "已收到确认，正在保存 Cookie。" in response.text


def test_capture_browser_login_cookies_warms_search_page_before_saving(tmp_path, monkeypatch):
    visited_urls = []
    launched_browser = {}
    service_holder = {}

    class FakePage:
        def __init__(self, context):
            self.context = context

        def goto(self, url, wait_until="domcontentloaded"):
            visited_urls.append(url)
            if "/search/" in url:
                self.context.cookie_map["SEARCH_RESULT_LIST_TYPE"] = "single"
            if "live.douyin.com" in url:
                self.context.cookie_map["webcast"] = "1"

    class FakeContext:
        def __init__(self):
            self.cookie_map = {
                "sessionid": "abc",
                "sessionid_ss": "abc",
                "msToken": "token-1",
                "s_v_web_id": "verify-1",
            }

        def new_page(self):
            return FakePage(self)

        def cookies(self):
            return [
                {"name": key, "value": value, "domain": ".douyin.com"}
                for key, value in self.cookie_map.items()
            ]

    class FakeBrowser:
        def new_context(self):
            return FakeContext()

    class FakeFirefox:
        def launch(self, **kwargs):
            launched_browser["engine"] = "firefox"
            return FakeBrowser()

    class FakeChromium:
        def launch(self, **kwargs):
            launched_browser["engine"] = "chromium"
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()
        firefox = FakeFirefox()

    class FakeSyncPlaywright:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyTaskManager:
        def submit(self, task_type, summary, runner):
            return runner()

    class DummyBroker:
        def publish(self, channel, payload):
            return None

    class DummyApi:
        home_url = "https://www.douyin.com/"

    monkeypatch.setattr("web.services.login_service.sync_playwright", lambda: FakeSyncPlaywright())
    def fake_sleep(_):
        service = service_holder["service"]
        state = service.pending_browser_sessions.get("browser-1") or {}
        if state.get("status") == "awaiting_confirm" and not state.get("confirm_requested"):
            service.confirm_browser_login("browser-1")

    monkeypatch.setattr("web.services.login_service.time.sleep", fake_sleep)
    monkeypatch.setattr("web.services.login_service.time.time", lambda: 0)

    service = LoginService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        DummyBroker(),
        api_cls=DummyApi,
    )
    service_holder["service"] = service
    service._validate_search_cookie = lambda cookie_str: None
    service._set_browser_login_state("browser-1", "waiting", False, "浏览器已打开，请完成登录")

    cookie_bundle = service._capture_browser_login_cookies("browser-1")

    assert visited_urls == [
        "https://www.douyin.com/",
        "https://www.douyin.com/search/%E4%B8%89%E8%A7%92%E6%B4%B2?type=general",
        "https://live.douyin.com/",
    ]
    assert launched_browser["engine"] == "chromium"
    assert "SEARCH_RESULT_LIST_TYPE=single" in cookie_bundle["douyin"]
    assert "webcast=1" in cookie_bundle["live"]


def test_capture_browser_login_cookies_requires_search_validation_before_returning(tmp_path, monkeypatch):
    service_holder = {}
    statuses = []
    validation_attempts = []

    class FakePage:
        def __init__(self, context):
            self.context = context

        def goto(self, url, wait_until="domcontentloaded"):
            if "/search/" in url:
                self.context.cookie_map["SEARCH_RESULT_LIST_TYPE"] = "single"
            if "live.douyin.com" in url:
                self.context.cookie_map["webcast"] = "1"

        def bring_to_front(self):
            return None

        def reload(self, wait_until="domcontentloaded"):
            self.context.cookie_map["SEARCH_RESULT_LIST_TYPE"] = "single"

    class FakeContext:
        def __init__(self):
            self.cookie_map = {
                "sessionid": "abc",
                "sessionid_ss": "abc",
                "msToken": "token-1",
                "s_v_web_id": "verify-1",
            }

        def new_page(self):
            return FakePage(self)

        def cookies(self):
            return [
                {"name": key, "value": value, "domain": ".douyin.com"}
                for key, value in self.cookie_map.items()
            ]

    class FakeBrowser:
        def new_context(self):
            return FakeContext()

    class FakeChromium:
        def launch(self, **kwargs):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeSyncPlaywright:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyTaskManager:
        def submit(self, task_type, summary, runner):
            return runner()

    class DummyBroker:
        def publish(self, channel, payload):
            return None

    class DummyApi:
        home_url = "https://www.douyin.com/"

    monkeypatch.setattr("web.services.login_service.sync_playwright", lambda: FakeSyncPlaywright())

    def fake_sleep(_):
        service = service_holder["service"]
        state = service.pending_browser_sessions.get("browser-1") or {}
        if state.get("status") in {"awaiting_confirm", "verification_required"} and not state.get("confirm_requested"):
            service.confirm_browser_login("browser-1")

    monkeypatch.setattr("web.services.login_service.time.sleep", fake_sleep)
    monkeypatch.setattr("web.services.login_service.time.time", lambda: 0)

    service = LoginService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        DummyBroker(),
        api_cls=DummyApi,
    )
    service_holder["service"] = service

    original_set_state = service._set_browser_login_state

    def record_state(session_id, status, done, message, **extra):
        statuses.append(status)
        return original_set_state(session_id, status, done, message, **extra)

    service._set_browser_login_state = record_state

    def validate_search_cookie(_cookie_str):
        validation_attempts.append("called")
        if len(validation_attempts) == 1:
            raise VerificationRequiredError("搜索 cookie 仍需验证")

    service._validate_search_cookie = validate_search_cookie
    service._set_browser_login_state("browser-1", "waiting", False, "浏览器已打开，请完成登录")

    cookie_bundle = service._capture_browser_login_cookies("browser-1")

    assert len(validation_attempts) == 2
    assert "verification_required" in statuses
    assert "SEARCH_RESULT_LIST_TYPE=single" in cookie_bundle["douyin"]
