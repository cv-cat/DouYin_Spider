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
        cookie_str = "cookie=ok"

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
