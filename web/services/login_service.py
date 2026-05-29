import asyncio
import base64
import io
import uuid

from dy_apis.login_api import DYLoginApi
import qrcode
from qrcode.image.svg import SvgImage
from web.services.session_service import SessionService


class LoginService:
    def __init__(self, db_path, task_manager, broker, api_cls=DYLoginApi):
        self.sessions = SessionService(db_path)
        self.task_manager = task_manager
        self.broker = broker
        self.api_cls = api_cls
        self.pending_qr_sessions = {}
        self.pending_phone_requests = {}

    def save_manual_cookie(self, scope, cookie_str):
        self.sessions.save_cookie(scope, cookie_str, status="manual")
        self.broker.publish("events", {"channel": "login", "message": "manual cookie saved"})
        return {"ok": True, "message": "manual cookie saved"}

    def _build_qr_image_data_url(self, verify_url):
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(verify_url)
        qr.make(fit=True)
        image = qr.make_image(image_factory=SvgImage)
        buffer = io.BytesIO()
        image.save(buffer)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/svg+xml;base64,{encoded}"

    def _cookie_string(self, auth):
        cookie = getattr(auth, "cookie", None)
        if isinstance(cookie, dict) and cookie:
            return "; ".join(f"{key}={value}" for key, value in cookie.items())
        return getattr(auth, "cookie_str", "")

    def _normalize_auth(self, auth):
        cookie = getattr(auth, "cookie", None)
        if not isinstance(cookie, dict):
            cookie = {}
            setattr(auth, "cookie", cookie)
        ms_token = getattr(auth, "msToken", None)
        if ms_token and "msToken" not in cookie:
            cookie["msToken"] = ms_token
        auth.cookie_str = self._cookie_string(auth)
        return auth

    def begin_qr_login(self):
        api = self.api_cls()
        auth = self._normalize_auth(asyncio.run(api.dyGenerateInitData(headless=True)))
        qr_payload = api.dyGenerateQRcode(auth)
        token = qr_payload["data"]["token"]
        verify_url = qr_payload["data"]["qrcode_index_url"]
        session_id = uuid.uuid4().hex
        self.pending_qr_sessions[session_id] = {
            "auth": auth,
            "token": token,
            "verify_url": verify_url,
        }
        return {
            "session_id": session_id,
            "status": "pending",
            "done": False,
            "verify_url": verify_url,
            "qr_image_data_url": self._build_qr_image_data_url(verify_url),
        }

    def poll_qr_login(self, session_id):
        pending = self.pending_qr_sessions.get(session_id)
        if pending is None:
            return {"session_id": session_id, "status": "missing", "done": True}
        api = self.api_cls()
        result = api.dyCheckQrCodeLogin(pending["auth"], pending["token"])
        status = str(result["data"]["status"])
        payload = {
            "session_id": session_id,
            "status": status,
            "done": status == "3",
            "verify_url": pending["verify_url"],
            "qr_image_data_url": self._build_qr_image_data_url(pending["verify_url"]),
            "raw": result,
        }
        if status == "3":
            self.sessions.save_cookie("douyin", self._cookie_string(pending["auth"]), status="qr-success")
            self.pending_qr_sessions.pop(session_id, None)
        return payload

    def request_phone_code(self, phone_num):
        if phone_num in self.pending_phone_requests:
            auth = self.pending_phone_requests[phone_num]
            result = self.api_cls().retryPhoneVerificationCode(phone_num, auth)
            if result.get("status") != "captcha_required":
                self.pending_phone_requests.pop(phone_num, None)
                self.sessions.save_cookie("douyin", self._cookie_string(auth), status="phone-code-requested")
            return result

        api = self.api_cls()
        auth = self._normalize_auth(asyncio.run(api.dyGenerateInitData(headless=True)))
        result = api.dyGeneratePhoneVerificationCode(phone_num, auth, interactive=False)
        self.sessions.save_cookie("douyin", self._cookie_string(auth), status="phone-code-bootstrap")
        if result.get("status") == "captcha_required":
            self.pending_phone_requests[phone_num] = auth
            return result
        self.sessions.save_cookie("douyin", self._cookie_string(auth), status="phone-code-requested")
        return result

    def finish_phone_login(self, phone_num, code):
        def runner():
            api = self.api_cls()
            auth = self.sessions.load_auth("douyin")
            if auth is None:
                raise RuntimeError("Missing phone-login bootstrap cookie")
            result, auth = api.dyPhoneVerificationCodeLogin(auth, phone_num, code)
            auth = self._normalize_auth(auth)
            self.sessions.save_cookie("douyin", self._cookie_string(auth), status="phone-login-success")
            return result

        return self.task_manager.submit("login.phone.finish", phone_num, runner)

    def persist_login_record(self, scope):
        api = self.api_cls()
        auth = self.sessions.load_auth(scope)
        if auth is None:
            raise RuntimeError(f"Missing {scope} cookie")
        auth = self._normalize_auth(auth)
        result = api.persistenceLoginInfo(auth)
        self.sessions.save_cookie(scope, self._cookie_string(auth), status="persisted")
        return result
