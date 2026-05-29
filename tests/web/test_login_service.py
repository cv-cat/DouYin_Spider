from web.services.login_service import LoginService
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
