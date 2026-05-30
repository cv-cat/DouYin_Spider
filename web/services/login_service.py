import asyncio
import base64
import io
import threading
import time
import urllib.parse
import uuid

from builder.auth import DouyinAuth
from dy_apis.douyin_api import DouyinAPI
from dy_apis.login_api import DYLoginApi
from playwright.sync_api import sync_playwright
import qrcode
from qrcode.image.svg import SvgImage
from web.services.crawl_service import VerificationRequiredError
from web.services.session_service import SessionService


class LoginService:
    def __init__(self, db_path, task_manager, broker, api_cls=DYLoginApi, browser_login_runner=None):
        self.sessions = SessionService(db_path)
        self.task_manager = task_manager
        self.broker = broker
        self.api_cls = api_cls
        self.browser_login_runner = browser_login_runner
        self.pending_qr_sessions = {}
        self.pending_phone_requests = {}
        self.pending_browser_sessions = {}

    def save_manual_cookie(self, scope, cookie_str):
        self.sessions.save_cookie(scope, cookie_str, status="manual")
        self.broker.publish("events", {"channel": "login", "message": "manual cookie saved"})
        return {"ok": True, "message": "manual cookie saved"}

    def begin_browser_login(self):
        session_id = uuid.uuid4().hex
        self._set_browser_login_state(session_id, "launching", False, "正在打开网页登录窗口")
        worker = threading.Thread(target=self._run_browser_login_session, args=(session_id,), daemon=True)
        worker.start()
        return self.poll_browser_login(session_id)

    def poll_browser_login(self, session_id):
        state = self.pending_browser_sessions.get(session_id)
        if state is None:
            return {
                "session_id": session_id,
                "status": "missing",
                "done": True,
                "message": "网页登录会话已失效，请重新启动。",
            }
        return dict(state)

    def confirm_browser_login(self, session_id):
        state = self.pending_browser_sessions.get(session_id)
        if state is None:
            return self.poll_browser_login(session_id)
        if state.get("done"):
            return dict(state)
        self._set_browser_login_state(
            session_id,
            "saving",
            False,
            "已收到确认，正在保存 Cookie。",
            confirm_requested=True,
        )
        return self.poll_browser_login(session_id)

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

    def _run_browser_login_session(self, session_id):
        try:
            if self.browser_login_runner is not None:
                cookie_bundle = self.browser_login_runner(session_id, self._set_browser_login_state)
            else:
                cookie_bundle = self._capture_browser_login_cookies(session_id)
            douyin_cookie = (cookie_bundle or {}).get("douyin", "").strip()
            live_cookie = (cookie_bundle or {}).get("live", "").strip() or douyin_cookie
            if not douyin_cookie:
                raise RuntimeError("未获取到 douyin cookie")
            self.sessions.save_cookie("douyin", douyin_cookie, status="browser-login-success")
            if live_cookie:
                self.sessions.save_cookie("live", live_cookie, status="browser-login-success")
            self._set_browser_login_state(
                session_id,
                "success",
                True,
                "网页登录成功，Cookie 已自动保存。",
                douyin_cookie=douyin_cookie,
                live_cookie=live_cookie,
            )
            self.broker.publish("events", {"channel": "login", "message": "browser cookie saved"})
        except Exception as exc:
            self._set_browser_login_state(
                session_id,
                "failed",
                True,
                f"{type(exc).__name__}: {exc}",
            )

    def _capture_browser_login_cookies(self, session_id):
        api = self.api_cls()
        home_url = getattr(api, "home_url", "https://www.douyin.com/")
        search_url = f"https://www.douyin.com/search/{urllib.parse.quote('三角洲')}?type=general"
        live_url = "https://live.douyin.com/"
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context()
            page = context.new_page()
            page.goto(home_url, wait_until="domcontentloaded")
            self._set_browser_login_state(session_id, "waiting", False, "浏览器已打开，请在新窗口完成登录。")
            deadline = time.time() + 300
            while time.time() < deadline:
                cookie_bundle = self._build_cookie_bundle(context.cookies())
                if self._has_login_cookie(cookie_bundle["douyin"]):
                    self._set_browser_login_state(session_id, "syncing", False, "检测到登录态，正在同步搜索 Cookie。")
                    search_page = None
                    try:
                        search_page = context.new_page()
                        search_page.goto(search_url, wait_until="domcontentloaded")
                        time.sleep(3)
                    except Exception:
                        pass
                    self._set_browser_login_state(session_id, "syncing", False, "搜索 Cookie 已同步，正在同步直播 Cookie。")
                    try:
                        live_page = context.new_page()
                        live_page.goto(live_url, wait_until="domcontentloaded")
                        time.sleep(3)
                    except Exception:
                        pass
                    self._set_browser_login_state(
                        session_id,
                        "awaiting_confirm",
                        False,
                        "已打开搜索页和直播页。请完成需要的验证后，回到后台点击“我已完成验证并保存 Cookie”。",
                    )
                    while time.time() < deadline:
                        self._wait_for_browser_confirmation(session_id, deadline)
                        cookie_bundle = self._build_cookie_bundle(context.cookies())
                        try:
                            self._validate_search_cookie(cookie_bundle["douyin"])
                            return cookie_bundle
                        except VerificationRequiredError:
                            self._set_browser_login_state(
                                session_id,
                                "verification_required",
                                False,
                                "当前 Cookie 仍需抖音搜索验证。请留在浏览器搜索页完成验证后，再点击“我已完成验证并保存 Cookie”。",
                                confirm_requested=False,
                            )
                            self._refresh_search_page(search_page)
                            self._set_browser_login_state(
                                session_id,
                                "awaiting_confirm",
                                False,
                                "搜索页已重新激活。请在浏览器完成验证后，再回到后台点击“我已完成验证并保存 Cookie”。",
                                confirm_requested=False,
                            )
                    raise TimeoutError("等待你确认保存 Cookie 超时")
                time.sleep(2)
            raise TimeoutError("等待网页登录超时")

    def _build_cookie_bundle(self, cookies):
        douyin_items = self._filter_douyin_cookies(cookies)
        cookie_str = "; ".join(f"{item['name']}={item['value']}" for item in douyin_items)
        return {
            "douyin": cookie_str,
            "live": cookie_str,
        }

    def _filter_douyin_cookies(self, cookies):
        filtered = []
        seen = set()
        for item in cookies:
            domain = str(item.get("domain") or "").lstrip(".").lower()
            if "douyin.com" not in domain:
                continue
            name = str(item.get("name") or "")
            if not name or name in seen:
                continue
            filtered.append(item)
            seen.add(name)
        return filtered

    def _has_login_cookie(self, cookie_str):
        return "sessionid=" in cookie_str or "sessionid_ss=" in cookie_str

    def _validate_search_cookie(self, cookie_str):
        auth = DouyinAuth()
        auth.perepare_auth(cookie_str, "", "")
        payload = DouyinAPI().search_general_work(auth, "三角洲", "0", "0", "0", "", "", "")
        search_nil_info = payload.get("search_nil_info") or {}
        search_nil_type = str(search_nil_info.get("search_nil_type") or "").strip().lower()
        status_msg = str(payload.get("status_msg") or "").strip().lower()
        if search_nil_type == "verify_check" or "verify" in status_msg or "captcha" in status_msg:
            raise VerificationRequiredError("当前 Cookie 仍需抖音搜索验证")

    def _refresh_search_page(self, search_page):
        if search_page is None:
            return
        try:
            search_page.bring_to_front()
        except Exception:
            pass
        try:
            search_page.reload(wait_until="domcontentloaded")
        except Exception:
            pass

    def _wait_for_browser_confirmation(self, session_id, deadline):
        while time.time() < deadline:
            state = self.pending_browser_sessions.get(session_id) or {}
            if state.get("confirm_requested"):
                return
            time.sleep(1)
        raise TimeoutError("等待你确认保存 Cookie 超时")

    def _set_browser_login_state(self, session_id, status, done, message, **extra):
        previous = self.pending_browser_sessions.get(session_id) or {}
        state = {
            "session_id": session_id,
            "status": status,
            "done": done,
            "message": message,
            "confirm_requested": previous.get("confirm_requested", False),
        }
        state.update(extra)
        self.pending_browser_sessions[session_id] = state
