import asyncio

from dy_apis.login_api import DYLoginApi
from web.services.session_service import SessionService


class LoginService:
    def __init__(self, db_path, task_manager, broker, api_cls=DYLoginApi):
        self.sessions = SessionService(db_path)
        self.task_manager = task_manager
        self.broker = broker
        self.api_cls = api_cls

    def save_manual_cookie(self, scope, cookie_str):
        self.sessions.save_cookie(scope, cookie_str, status="manual")
        self.broker.publish("events", {"channel": "login", "message": "manual cookie saved"})
        return {"ok": True, "message": "manual cookie saved"}

    def start_qr_login(self):
        def runner():
            api = self.api_cls()
            auth = asyncio.run(api.dyGenerateInitData(headless=True))
            qr_payload = api.dyGenerateQRcode(auth)
            token = qr_payload["data"]["token"]
            for _ in range(60):
                result = api.dyCheckQrCodeLogin(auth, token)
                status = result["data"]["status"]
                if status == "3":
                    self.sessions.save_cookie("douyin", auth.cookie_str, status="qr-success")
                    return {"status": status}
            raise TimeoutError("QR login polling timed out")

        return self.task_manager.submit("login.qr", "qr login", runner)

    def start_phone_code_request(self, phone_num):
        def runner():
            api = self.api_cls()
            auth = asyncio.run(api.dyGenerateInitData(headless=True))
            result = api.dyGeneratePhoneVerificationCode(phone_num, auth)
            self.sessions.save_cookie("douyin", auth.cookie_str, status="phone-code-requested")
            return result

        return self.task_manager.submit("login.phone.request_code", phone_num, runner)

    def finish_phone_login(self, phone_num, code):
        def runner():
            api = self.api_cls()
            auth = self.sessions.load_auth("douyin")
            if auth is None:
                raise RuntimeError("Missing phone-login bootstrap cookie")
            result, auth = api.dyPhoneLogin(phone_num, code, auth)
            self.sessions.save_cookie("douyin", auth.cookie_str, status="phone-login-success")
            return result

        return self.task_manager.submit("login.phone.finish", phone_num, runner)
