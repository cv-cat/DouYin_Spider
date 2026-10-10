import base64
import http.cookiejar
import hashlib
import json
import os
import time
import uuid

from dy_apis import douyin_api
from utils.dy_util import (trans_cookies, generate_msToken, generate_dynamic_msToken,
                           generate_s_v_web_id)
from utils.dtrait_profile import load_dtrait_profile

from utils.http_client import _Response

# msToken 缓存有效期（秒）：过期后下次访问自动重新换取
_MS_TTL = 600


class DouyinAuth:
    def __init__(self):
        self.cookie = None
        self._cookie_str = None
        self._raw_cookie_tokens = []
        # Provenance is deliberately kept separate from the Cookie mapping.
        # Opaque anonymous values must never be mistaken for locally
        # reproducible algorithms merely because their length is correct.
        self._cookie_sources = {}
        self._cookie_source_events = []
        self.private_key = None
        self.ticket = None
        self.ts_sign = None
        self.client_cert = None
        self.ree_public_key = None
        self.uid = None
        self.server_cert = None  # passport 下发的 ecies 服务端证书
        # x-tt-session-dtrait：设备特征头，三种来源，优先级从高到低——
        #   session_dtrait  直接给成品头
        #   dtrait_blob     给内层 blob，外层由 utils/dtrait.py 按 path 现算
        #   dtrait_profile  给设备档案，内层 blob 也由 utils/dtrait_features.py 现算
        self.dtrait_blob = None
        try:
            self.dtrait_profile = load_dtrait_profile()
        except (OSError, ValueError, KeyError, TypeError):
            # Keep construction usable when a deployment intentionally ships
            # without the checked-in profile; strict request paths will still
            # fail closed if no explicit dtrait material is supplied.
            self.dtrait_profile = None
        self.session_dtrait = None
        # x-tt-passport-verify-portrait（`<uuid>.login`），登录期间 passport 请求要带
        self.verify_portrait = None
        # One-shot ticket returned by passport/web/send_code for the SMS
        # login flow.  It is session state only and is deliberately not
        # persisted with long-lived credentials.
        self.mobile_ticket = None
        self._sms_sent_at = None
        self.phone_login_profile = None
        # Phone login sets this when it is running against the browser-
        # evidence contract.  Keep it explicit so helpers can fail closed
        # instead of silently synthesizing missing wire state.
        self.strict_browser_alignment = False
        self._proxies = None
        self._trait_pk_cache = {}
        # Chrome reuses the RSA-encrypted AES session key in
        # x-tt-session-dtrait across requests; only IV/payload changes per
        # pathname.  Cache the first segment per (aid, origin, blob, key).
        self._dtrait_material_cache = {}
        self._dtrait_last_evidence = None
        self._ttwid = ""
        self._webid = ""         # 真实设备号缓存
        self._webid_resolving = False
        self._ms_cache = ""      # 动态 msToken 缓存
        self._ms_ts = 0          # 缓存时间戳
        # PC IM obtains a short-lived identity-security token immediately
        # before message/send.  Keep it on the same Auth instance so callers
        # can reuse a token during a burst, while retaining the device id
        # returned alongside it for the protobuf header map.
        self.identity_security_token = ""
        self.identity_security_device_id = ""
        self.identity_security_token_ts = 0
        # Passport's encrypted account_sdk_source_info is a page-session
        # measurement.  Chrome reuses it across challenge/send_code/sms_login;
        # keep the cached value and the two role-specific ``browser.t`` values
        # on Auth instead of regenerating them per request.
        self._passport_sdk_source_info = ""
        self._t_suffix = ""
        self._t_query = ""
        self._t_cookie = ""
        # QR login owns the mssdk lifecycle while polling.  During that
        # window the token is rotated by /web/common on Chrome's timer, not by
        # the generic 600-second /web/r/token cache path.
        self._ms_pinned = False
        self._ecdh_cache = {}    # (aid, origin) -> 32 字节 HMAC 密钥 / None
        self.http = None          # creator 全链路持久 curl_cffi Session
        self._http_seeded = False
        self._session_cookie_names = set()
        self._session_cookie_scopes = {}
        self._session_cookie_values = {}
        self.creator_csrf_token = ""
        self.creator_bootstrapped = False
        # Capability verification is intentionally separate from capability
        # construction.  A shared Auth/session can be wired for live or
        # creator traffic without having contacted those services yet.
        self.live_rest_verified = False
        self.live_websocket_connected = False
        self.live_websocket_verified = False
        self.main_read_verified = False
        self.creator_read_verified = False
        self.creator_upload_verified = False
        self.publish_attempted = False
        self.publish_server_verified = False
        # Optional wire-exact Cookie header captured from the browser.  This
        # deliberately stays separate from the CookieJar: duplicate names
        # with different scopes must survive exactly as sent by Chromium.
        self._creator_cookie_override = ""
        self._creator_cookie_template = []

    def perepare_auth(self, cookieStr: str, web_protect_: str = "", keys_: str = ""):
        self.cookie = trans_cookies(cookieStr)
        # ``trans_cookies`` keeps Chromium's occasional no-equals cookie
        # tokens (for example ``douyin.com``) on a sidecar because a normal
        # mapping cannot serialize that wire form without changing it.
        self._raw_cookie_tokens = list(
            getattr(self.cookie, "raw_tokens", ()) or ()
        )
        # Let the compatibility HTTP facade discover the owning Auth when a
        # legacy API still passes ``cookies=auth.cookie`` to a module-level
        # request helper.  The reference is process-local only and is never
        # serialized into the Cookie header.
        try:
            self.cookie._auth_owner = self
        except Exception:
            pass
        self._cookie_sources = {
            name: "captured_input" for name in self.cookie.keys()
        }
        self._cookie_source_events = []
        self._ttwid = self.cookie.get("ttwid", "")
        # 真实请求 msToken 只在 query 携带；cookie 里若有旧 msToken 去掉，避免冲突
        self.cookie.pop("msToken", None)
        # verifyFp / fp 取自 s_v_web_id，必须与随请求发出的 cookie 一致；缺失就自己生成
        if not self.cookie.get("s_v_web_id"):
            self.cookie["s_v_web_id"] = generate_s_v_web_id()
        self._sync_cookie_str()
        if web_protect_ != "":
            web_protect_ = json.loads(json.loads(web_protect_)['data'])
            self.ticket = web_protect_['ticket']
            self.ts_sign = web_protect_['ts_sign']
            self.client_cert = web_protect_['client_cert']
        if keys_ != "":
            keys_ = json.loads(json.loads(keys_)['data'])
            self.private_key = keys_['ec_privateKey']
            self.ree_public_key = base64.b64encode(self.private_key.encode()).decode()

    def _serialize_cookie_str(self):
        cookie = getattr(self, "cookie", None) or {}
        raw = list(getattr(self, "_raw_cookie_tokens", ()) or ())
        parts = [
            name if name in raw else f"{name}={value}"
            for name, value in cookie.items()
        ]
        parts.extend(token for token in raw if token not in cookie)
        return "; ".join(parts)

    @property
    def cookie_str(self):
        """Always reflect the current Cookie mapping on read.

        A number of bootstrap paths update ``auth.cookie`` directly.  A plain
        string attribute can therefore become stale between two requests.
        Re-serializing on read makes the mapping and wire Cookie header a
        single source of truth while preserving the caller's bare tokens.
        """
        if getattr(self, "cookie", None) is None:
            return self._cookie_str
        return self._serialize_cookie_str()

    @cookie_str.setter
    def cookie_str(self, value):
        # Keep compatibility with existing callers that assign the field;
        # subsequent reads intentionally derive from ``cookie`` instead.
        self._cookie_str = value

    def _sync_cookie_str(self):
        """Serialize ``cookie`` without losing Chromium bare tokens.

        Cookie values are updated by several independent bootstrap helpers.
        Keeping this operation in one place prevents ``cookie`` and
        ``cookie_str`` from silently diverging after a Set-Cookie merge.
        ``_raw_cookie_tokens`` contains the rare no-equals tokens observed in
        browser captures and must remain verbatim on the wire.
        """
        self._cookie_str = self._serialize_cookie_str()
        return self._cookie_str

    @classmethod
    def from_cookie(cls, cookie_str, *, ticket=None, ts_sign=None,
                    client_cert=None, private_key=None, dtrait_blob=None,
                    session_dtrait=None, bootstrap_creator=True, proxies=None):
        """从完整 Cookie 构造 Auth；可选自动初始化 creator 子域状态。"""
        # A pasted browser Cookie is often accompanied by the ticket-guard and
        # dtrait values in the project's .env.  Resolve those defaults here so
        # callers that only provide CK still receive the complete Auth object;
        # explicit arguments always win.
        try:
            from dotenv import load_dotenv
            load_dotenv(".env")
        except Exception:
            pass
        # Security material is session-bound.  Reusing a ticket/private key
        # from a different account's `.env` alongside an explicitly pasted CK
        # makes read calls appear healthy but causes creator writes to fail (or
        # worse, binds the new CK to the old browser session).  Environment
        # defaults are therefore consumed only when the supplied CK is the same
        # CK stored in `.env`; callers can still override every field
        # explicitly.  Device dtrait is also kept scoped to the matching CK so
        # a different user's browser profile is never silently mixed in.
        env_cookie = os.getenv("DY_COOKIES") or ""

        def _cookie_fingerprint(value):
            pairs = []
            for token in str(value or "").split(";"):
                name, sep, item = token.strip().partition("=")
                if name and sep:
                    pairs.append((name, item))
            return tuple(sorted(pairs))

        supplied_cookie = str(cookie_str or "").strip()
        same_env_session = bool(env_cookie) and (
            _cookie_fingerprint(supplied_cookie)
            == _cookie_fingerprint(env_cookie)
        )

        def _env_default(name):
            return os.getenv(name) or None if same_env_session else None

        ticket = ticket if ticket is not None else _env_default("DY_TICKET")
        ts_sign = ts_sign if ts_sign is not None else _env_default("DY_TS_SIGN")
        client_cert = (client_cert if client_cert is not None
                       else _env_default("DY_CLIENT_CERT"))
        private_key = (private_key if private_key is not None
                       else _env_default("DY_PRIVATE_KEY"))
        dtrait_blob = (dtrait_blob if dtrait_blob is not None
                       else _env_default("DY_DTRAIT_BLOB"))
        session_dtrait = (session_dtrait if session_dtrait is not None
                          else _env_default("DY_SESSION_DTRAIT"))
        auth = cls()
        auth._proxies = proxies
        auth.perepare_auth(cookie_str or "", "", "")
        auth.ticket = ticket
        auth.ts_sign = ts_sign
        auth.client_cert = client_cert
        auth.private_key = private_key
        auth.dtrait_blob = dtrait_blob
        auth.session_dtrait = session_dtrait
        # A pasted browser CK often contains __ac_nonce but omits the
        # short-lived __ac_signature.  Complete that page-JS step once while
        # constructing Auth; if the caller already supplied a signature it is
        # preserved byte-for-byte.  Missing nonce remains a server/browser
        # bootstrap concern and is not synthesized here.
        if auth.cookie.get("__ac_nonce") and not auth.cookie.get("__ac_signature"):
            try:
                from dy_apis.login_api import DYLoginApi
                DYLoginApi._apply_ac_signature(auth, strict=False)
            except Exception:
                pass
        auth.ensure_http_session()
        if bootstrap_creator:
            auth.bootstrap_creator_session(proxies=proxies)
        return auth

    @classmethod
    def from_qrcode_login(cls, *, timeout=300, show_qr=True, on_qrcode=None,
                          bootstrap_creator=True, proxies=None):
        """运行现有纯 HTTP 二维码登录，并返回可直接发布的 creator Auth。"""
        from dy_apis.login_api import DYLoginApi

        auth = DYLoginApi().qrcode_login(
            timeout=timeout, show_qr=show_qr, on_qrcode=on_qrcode,
            proxies=proxies,
        )
        auth._proxies = proxies
        auth.ensure_http_session()
        if bootstrap_creator:
            auth.bootstrap_creator_session(proxies=proxies)
        return auth

    @classmethod
    def open(cls, cookie_str=None, *, login_type="auto", phone=None,
             code=None, auth=None, ticket=None, ts_sign=None,
             client_cert=None, private_key=None, dtrait_blob=None,
             session_dtrait=None, timeout=300, show_qr=True,
             on_qrcode=None, bootstrap_creator=True, proxies=None):
        """Open one reusable Auth for cookie, QR, or phone login.

        This is the single high-level entry point for callers.  A supplied
        Cookie is consumed as-is and upgraded on the same session; an empty
        Cookie selects a real login flow.  Phone login is intentionally a
        two-step operation: with ``code=None`` this returns ``(auth,
        response)`` after sending the SMS, and the caller must pass that same
        ``auth`` back with the code.  No second Auth is ever created between
        ``send_code`` and ``sms_login``.
        """
        # Keep the high-level library entry point consistent with the CLI:
        # an omitted argument consumes the user's explicitly configured
        # ``DY_COOKIES`` from .env; only when both are empty do we start QR/SMS
        # login.  Explicit ``cookie_str`` always wins over the environment.
        if cookie_str is None:
            try:
                from dotenv import load_dotenv
                load_dotenv(".env")
            except Exception:
                pass
            cookie_str = os.getenv("DY_COOKIES") or ""
        supplied = str(cookie_str or "").strip()
        mode = (login_type or "auto").strip().lower()
        if mode in {"qr", "qrcode", "scan", "扫码"}:
            mode = "qrcode"
        elif mode in {"sms", "phone", "mobile", "手机号"}:
            mode = "phone"
        elif mode in {"cookie", "ck", "cookies"}:
            mode = "cookie"
        elif mode == "auto":
            mode = "cookie" if supplied else ("phone" if phone else "qrcode")
        else:
            raise ValueError(f"不支持的 login_type: {login_type}")

        if mode == "cookie":
            if not supplied:
                # An empty explicit cookie must not create a half-initialized
                # anonymous Auth.  Fall through to the actual login flow.
                mode = "phone" if phone else "qrcode"
            else:
                return cls.from_cookie(
                    supplied, ticket=ticket, ts_sign=ts_sign,
                    client_cert=client_cert, private_key=private_key,
                    dtrait_blob=dtrait_blob, session_dtrait=session_dtrait,
                    bootstrap_creator=bootstrap_creator, proxies=proxies,
                )

        if mode == "qrcode":
            return cls.from_qrcode_login(
                timeout=timeout, show_qr=show_qr, on_qrcode=on_qrcode,
                bootstrap_creator=bootstrap_creator, proxies=proxies,
            )

        if not phone:
            raise ValueError("手机号登录需要 phone")
        if code is None or str(code).strip() == "":
            return cls.start_phone_login(phone, proxies=proxies)
        if auth is None:
            raise ValueError(
                "提交手机号验证码必须传入发送验证码时返回的同一个 auth"
            )
        return cls.from_phone_login(
            phone, code, auth=auth, bootstrap_creator=bootstrap_creator,
            proxies=proxies,
        )

    def live_auth(self, cookie_str=None):
        """Return the live API session backed by this Auth.

        Live REST and WebSocket endpoints accept the same main-site Cookie in
        current captures.  Keeping the default on ``self`` avoids a second
        login/session.  An explicit live Cookie remains available for legacy
        deployments that deliberately use a separate browser profile.
        """
        if not str(cookie_str or "").strip():
            return self
        return type(self).from_cookie(
            cookie_str, bootstrap_creator=False, proxies=self._proxies,
        )

    @classmethod
    def start_phone_login(cls, phone, *, proxies=None):
        """Bootstrap a phone login and send one SMS code.

        Returns ``(auth, response)``.  Keep the returned ``auth`` and pass it
        to :meth:`from_phone_login` after the user enters the code; creating a
        second auth would change the cookie/device session the browser keeps
        between ``send_activation_code`` and ``quick_login``.
        """
        from dy_apis.login_api import DYLoginApi

        api = DYLoginApi()
        # The phone form embedded by https://www.douyin.com/jingxuan is not
        # the bare login.douyin.com aid=24 SSO page.  Chrome first runs the
        # normal passport bootstrap (ttwid/check -> challenge -> ticket guard)
        # and the form then submits /passport/web/send_code and /sms_login.
        # Keep the aid=24 SSO page available only as an explicit profile.
        import os
        profile = (os.getenv("DY_PHONE_LOGIN_PROFILE") or "passport_web").strip().lower()
        if profile in {"sso", "phone_sso", "login_page"}:
            auth = api.bootstrap_phone_auth(proxies=proxies)
        else:
            # The jingxuan SMS flow is the strict, browser-evidence path.
            # Do not allow bootstrap to continue with synthetic challenge
            # cookies or missing device headers.
            auth = api.bootstrap_auth(strict=True, proxies=proxies)
        response = api.send_sms_code(auth, phone)
        return auth, response

    @classmethod
    def from_phone_login(cls, phone, code, *, auth=None,
                         bootstrap_creator=True, proxies=None):
        """Submit a code on the same auth returned by ``start_phone_login``."""
        from dy_apis.login_api import DYLoginApi

        if auth is None:
            raise ValueError(
                "手机号验证码必须在发送验证码的同一会话提交；请先调用 "
                "DouyinAuth.start_phone_login(phone)，再把返回的 auth 传入"
            )
        if proxies is not None:
            auth._proxies = proxies
        api = DYLoginApi()
        api.phone_login(auth, phone, code)
        auth.ensure_http_session()
        if bootstrap_creator:
            auth.bootstrap_creator_session(proxies=proxies)
        return auth

    def ensure_http_session(self):
        """创建持久 TLS/HTTP2/Cookie 会话，并把主域 Cookie 按 domain 写入 jar。"""
        if self.http is None:
            from utils.http_client import Session
            self.http = Session()
        # The login/bootstrap code may mutate ``auth.cookie`` after the
        # Session was first created (for example local ``bit_env`` derivation,
        # acrawler ``__ac_signature`` or a later Set-Cookie merge).  Mirror
        # those changes before every request so legacy call sites that route
        # through this Auth cannot accidentally send a stale jar.
        current = {
            str(name): str(value)
            for name, value in (self.cookie or {}).items()
            if name and value is not None
        }
        # These names are host-only in Chromium's www.douyin.com captures;
        # placing them on ``.douyin.com`` would leak page/device state to
        # login, live and creator subdomains.  Keep the list local to avoid a
        # builder -> login_api import cycle during Auth construction.
        www_only = {
            "s_v_web_id", "__ac_nonce", "__ac_signature",
            "x-web-secsdk-uid", "dy_swidth", "dy_sheight",
            "device_web_cpu_core", "device_web_memory_size",
            "architecture", "fpk1", "fpk2",
        }
        for name, value in current.items():
            scope = "www.douyin.com" if name in www_only else ".douyin.com"
            if (self._session_cookie_values.get(name) == value
                    and self._session_cookie_scopes.get(name) == scope):
                continue
            # A name may have been seeded on the old shared scope by a prior
            # call or by a response. Remove only the tracked Auth copy before
            # moving it to its browser-accurate scope; creator host-only
            # copies are not tracked and are left untouched.
            old_scope = self._session_cookie_scopes.get(name)
            if old_scope and old_scope != scope:
                try:
                    self.http.cookies.jar.clear(old_scope, "/", name)
                except KeyError:
                    pass
            self.http.cookies.set(
                name, value, domain=scope, path="/", secure=True,
            )
            self._session_cookie_values[name] = value
            self._session_cookie_scopes[name] = scope
        # Remove only the shared-domain entries previously seeded by Auth;
        # creator host-only/domain-scoped cookies belong to the creator
        # template and must survive this synchronization.
        stale = self._session_cookie_names.difference(current)
        for name in stale:
            try:
                self.http.cookies.jar.clear(
                    self._session_cookie_scopes.get(name, ".douyin.com"),
                    "/", name,
                )
            except KeyError:
                pass
            self._session_cookie_values.pop(name, None)
            self._session_cookie_scopes.pop(name, None)
        self._session_cookie_names = set(current)
        self._http_seeded = True
        return self.http

    def request(self, method, url, **kwargs) -> _Response:
        """使用 Auth 拥有的持久会话发送请求。"""
        session = self.ensure_http_session()
        # Legacy endpoints pass ``cookies=self.cookie`` even though this
        # Auth-owned Session already has the same jar.  Suppress that
        # duplicate parameter; curl_cffi otherwise serializes the mapping in
        # addition to the jar and can emit duplicate Cookie pairs.
        if kwargs.get("cookies") is self.cookie:
            kwargs = dict(kwargs)
            kwargs.pop("cookies", None)
        if kwargs.get("proxies") is None and self._proxies is not None:
            kwargs["proxies"] = self._proxies
        split_cookie_header = bool(kwargs.pop("split_cookie_header", False))
        headers = kwargs.get("headers") or {}
        cookie_header = next(
            (value for name, value in headers.items() if name.lower() == "cookie"),
            None,
        )
        if cookie_header is not None:
            # Session 会临时清空 jar，避免显式 Cookie 与自动 Cookie 叠加；
            # 保留原字典则可同时保留调用方指定的 HTTP/2 wire 位置。
            kwargs["headers"] = dict(headers)
            response = session.request_with_cookie_header(
                method, url, cookie_header,
                split_cookie_header=split_cookie_header,
                on_fresh_cookies=self._refresh_creator_cookie_template,
                **kwargs,
            )
            # Explicit Cookie-header callers (currently creator parity paths)
            # already receive scoped Set-Cookie updates through
            # ``_refresh_creator_cookie_template``.  Do not flatten those
            # host-only creator cookies into ``auth.cookie`` here; doing so
            # would reseed them on the shared .douyin.com domain next time.
            return response
        response = session.request(method, url, **kwargs)
        # Keep the flattened mapping/provenance ledger in sync for legacy
        # callers that route through ``requests.get(..., cookies=auth.cookie)``.
        # The persistent curl Session already stores these values in its jar;
        # this merge only mirrors response Set-Cookie into Auth state.
        try:
            from utils.passport import merge_set_cookies
            merge_set_cookies(self, response.cookies.get_dict())
        except Exception:
            pass
        return response

    def _refresh_creator_cookie_template(self, fresh_cookies):
        """按 Chromium 的 Set-Cookie 更新时间重排模板中的同 scope occurrence。"""
        if not fresh_cookies:
            return

        def scope_of(cookie):
            if (
                cookie.domain == "creator.douyin.com"
                and not cookie.domain_specified
            ):
                return "host-only"
            return cookie.domain.lstrip(".")

        for cookie in fresh_cookies:
            scope = scope_of(cookie)
            if scope not in {"host-only", "creator.douyin.com", "douyin.com"}:
                continue
            matched = False
            retained = []
            for entry in self._creator_cookie_template:
                if (
                    not matched
                    and entry["name"] == cookie.name
                    and entry["scope"] == scope
                    and entry["path"] == cookie.path
                ):
                    matched = True
                    continue
                retained.append(entry)
            if matched or self._creator_cookie_template:
                retained.append({
                    "name": cookie.name,
                    "scope": scope,
                    "path": cookie.path,
                })
                self._creator_cookie_template = retained
            if scope == "douyin.com" and self.cookie is not None:
                self.cookie[cookie.name] = cookie.value
        if self.cookie is not None:
            self.cookie_str = "; ".join(
                f"{name}={value}" for name, value in self.cookie.items()
            )

    def cookie_header_for_url(self, url, method="GET"):
        return self.ensure_http_session().cookie_header(url, method=method)

    def _set_host_only_cookie(self, host, name, value, *, path="/", secure=True):
        """向 curl CookieJar 写入真正 host-only（无 Domain 属性）的 Cookie。"""
        cookie = http.cookiejar.Cookie(
            version=0, name=str(name), value=str(value), port=None,
            port_specified=False, domain=str(host), domain_specified=False,
            domain_initial_dot=False, path=path, path_specified=True,
            secure=secure, expires=None, discard=True, comment=None,
            comment_url=None, rest={}, rfc2109=False,
        )
        self.ensure_http_session().cookies.jar.set_cookie(cookie)

    @property
    def creator_cookie_str(self):
        session = self.ensure_http_session()
        # request_with_cookie_header() 会在同一把锁内临时清空 CookieJar；
        # 先在锁内完成快照，避免封面轮询线程把主线程的 Cookie 读成空串。
        with session.locked():
            cookies = list(session.cookies.jar)
        if self._creator_cookie_template:
            used = set()
            ordered = []

            def matches(cookie, entry):
                if cookie.name != entry["name"] or cookie.path != entry["path"]:
                    return False
                if entry["scope"] == "host-only":
                    return (
                        cookie.domain == "creator.douyin.com"
                        and not cookie.domain_specified
                    )
                return cookie.domain.lstrip(".") == entry["scope"]

            for entry in self._creator_cookie_template:
                for index, cookie in enumerate(cookies):
                    if index not in used and matches(cookie, entry):
                        used.add(index)
                        ordered.append(cookie)
                        break

            # Chromium appends cookies newly created after the captured
            # request. Preserve the captured order first, then the CookieJar
            # creation order for genuine response additions.
            for index, cookie in enumerate(cookies):
                if index not in used and (
                    cookie.domain.lstrip(".") in {
                        "douyin.com", "creator.douyin.com",
                    }
                ):
                    ordered.append(cookie)
            return "; ".join(
                f"{cookie.name}={cookie.value}" for cookie in ordered
            )
        if self._creator_cookie_override:
            return self._creator_cookie_override
        used = set()

        def take(name, predicate=lambda cookie: True):
            for index, cookie in enumerate(cookies):
                if index not in used and cookie.name == name and predicate(cookie):
                    used.add(index)
                    return cookie
            return None

        host_only = lambda cookie: (
            cookie.domain == "creator.douyin.com" and not cookie.domain_specified
        )
        creator_domain = lambda cookie: cookie.domain.lstrip(".") == "creator.douyin.com"
        shared_domain = lambda cookie: cookie.domain.lstrip(".") == "douyin.com"
        ordered = []
        for name, predicate in (
            ("gd_random", host_only),
            ("x-web-secsdk-uid", host_only),
            ("gfkadpd", creator_domain),
            ("_tea_utm_cache_2906", creator_domain),
            ("csrf_session_id", host_only),
            ("bd_ticket_guard_client_web_domain", shared_domain),
            ("s_v_web_id", host_only),
            ("s_v_web_id", shared_domain),
            ("bd_ticket_guard_client_data", shared_domain),
        ):
            cookie = take(name, predicate)
            if cookie is not None:
                ordered.append(cookie)
        # 主域其余 Cookie 保持扫码 Cookie 串的原始顺序。
        for name in (self.cookie or {}):
            cookie = take(name, shared_domain)
            if cookie is not None:
                ordered.append(cookie)
        for index, cookie in enumerate(cookies):
            if index not in used and (
                cookie.domain.lstrip(".") in {"douyin.com", "creator.douyin.com"}
            ):
                ordered.append(cookie)
        return "; ".join(f"{cookie.name}={cookie.value}" for cookie in ordered)

    def import_creator_browser_cookies(self, cookie_header, cookie_store=None):
        """导入 Chrome Cookie 线序，同时允许 Set-Cookie 动态刷新其值。

        ``cookie_header`` 保留网络面板中的顺序和同名项；``cookie_store``
        提供非 HttpOnly Cookie 的 domain/path，用于区分 host-only 与共享域。
        HttpOnly 项在 creator 请求里均按共享 ``douyin.com`` 域处理。
        """
        session = self.ensure_http_session()
        pairs = []
        for part in str(cookie_header or "").split(";"):
            name, separator, value = part.strip().partition("=")
            if separator and name:
                pairs.append((name, value))

        scoped = []
        for item in cookie_store or []:
            name = str(item.get("name") or "")
            if not name:
                continue
            domain = item.get("domain")
            scoped.append({
                "name": name,
                "value": str(item.get("value") or ""),
                "scope": "host-only" if domain is None else str(domain).lstrip("."),
                "path": str(item.get("path") or "/"),
            })

        # CookieStore does not expose HttpOnly cookies. These creator cookies
        # have stable scopes in Chrome captures and must not be left as the
        # flattened shared-domain copies created by perepare_auth().
        inferred_scopes = {
            "gd_random": "host-only",
            "csrf_session_id": "host-only",
            "gfkadpd": "creator.douyin.com",
            "_tea_utm_cache_2906": "creator.douyin.com",
        }
        for name, value in pairs:
            scope = inferred_scopes.get(name)
            if scope and not any(
                item["name"] == name and item["value"] == value
                for item in scoped
            ):
                scoped.append({
                    "name": name, "value": value,
                    "scope": scope, "path": "/",
                })

        # Bind each wire occurrence to a scope. Prefer the exact CookieStore
        # value, but fall back to same-name occurrence order because a cookie
        # can rotate between the captured request and the CookieStore read.
        available = list(scoped)
        template = []
        for name, value in pairs:
            match_index = next((
                index for index, item in enumerate(available)
                if item["name"] == name and item["value"] == value
            ), None)
            if match_index is None:
                match_index = next((
                    index for index, item in enumerate(available)
                    if item["name"] == name
                ), None)
            if match_index is None:
                scope = inferred_scopes.get(name, "douyin.com")
                item = {"scope": scope, "path": "/"}
            else:
                item = available.pop(match_index)
            template.append({
                "name": name, "value": value,
                "scope": item["scope"], "path": item["path"],
            })

        # Remove flattened/bootstrap copies and seed the exact values from the
        # captured request. CookieStore is used only for scope metadata, never
        # as a later-in-time value source.
        template_names = {item["name"] for item in template}
        for cookie in list(session.cookies.jar):
            if cookie.name in template_names and cookie.domain.lstrip(".") in {
                "douyin.com", "creator.douyin.com",
            }:
                try:
                    session.cookies.jar.clear(
                        cookie.domain, cookie.path, cookie.name,
                    )
                except KeyError:
                    pass
        for item in template:
            if item["scope"] == "host-only":
                self._set_host_only_cookie(
                    "creator.douyin.com", item["name"], item["value"],
                    path=item["path"],
                )
            else:
                session.cookies.set(
                    item["name"], item["value"],
                    domain=f'.{item["scope"]}', path=item["path"], secure=True,
                )
        self._creator_cookie_override = ""
        self._creator_cookie_template = [
            {key: item[key] for key in ("name", "scope", "path")}
            for item in template
        ]
        return self

    def mark_cookie_source(self, name, source, *, detail=""):
        """Record where a Cookie value came from.

        ``source`` is intentionally a small vocabulary used by the parity
        audits: ``captured_input``, ``server_set_cookie``, ``browser_runtime``,
        ``node_page_js``, ``local_pure_conditional``,
        ``runtime_response_unclassified`` and
        ``unproven_synthetic``.  This metadata is not sent on the wire and is
        safe to inspect in diagnostics.
        """
        if not name:
            return
        value = str(source or "unknown")
        self._cookie_sources[name] = value
        self._cookie_source_events.append({
            "name": str(name), "source": value,
            "detail": str(detail or ""), "time": time.time(),
        })

    def cookie_source(self, name):
        return (getattr(self, "_cookie_sources", {}) or {}).get(name, "unknown")

    def cookie_evidence(self):
        """Return a JSON-safe snapshot of Cookie values and provenance."""
        return {
            name: {
                "length": len(str(value)),
                "source": self.cookie_source(name),
            }
            for name, value in (getattr(self, "cookie", None) or {}).items()
        }

    def capability_report(self):
        """Summarize what this Auth can safely drive right now.

        The report is deliberately a capability/status view, not a promise
        that the platform will accept every request (risk controls and room
        state remain server-side).  It is useful for one-click workflows to
        fail before a write operation when a required credential is absent.
        """
        try:
            from dy_apis.login_api import anonymous_cookie_evidence
            anonymous = anonymous_cookie_evidence(self)
        except Exception:
            anonymous = {}
        publish_missing = [
            label for attr, label in (
                ("ticket", "ticket"), ("ts_sign", "ts_sign"),
                ("private_key", "private_key"),
            ) if not getattr(self, attr, None)
        ]
        if not (getattr(self, "dtrait_blob", None)
                or getattr(self, "dtrait_profile", None)):
            publish_missing.append("dtrait_blob/profile")
        return {
            "shared_auth": True,
            "cookie_count": len(self.cookie or {}),
            "login_cookie_present": bool((self.cookie or {}).get("sessionid")),
            "read_only_ready": bool((self.cookie or {}).get("sessionid")),
            "main_read_verified": bool(self.main_read_verified),
            "anonymous_cookie_evidence": anonymous,
            "creator_bootstrapped": bool(self.creator_bootstrapped),
            "creator_read_verified": bool(self.creator_read_verified),
            "creator_upload_material_ready": bool(self.creator_bootstrapped),
            "creator_upload_verified": bool(self.creator_upload_verified),
            "one_click_read_paths": {
                "main_site": bool(self.main_read_verified),
                "live_rest": bool(self.live_rest_verified),
                "creator_read": bool(self.creator_read_verified),
            },
            "publish_security_ready": not publish_missing
                and self.ticket_matches_session(),
            "publish_security_missing": publish_missing,
            "publish_attempted": bool(self.publish_attempted),
            "publish_server_verified": bool(self.publish_server_verified),
            "live_rest_uses_same_auth": True,
            "live_rest_verified": bool(self.live_rest_verified),
            "live_websocket_uses_same_auth": True,
            "live_websocket_connected": bool(self.live_websocket_connected),
            "live_websocket_verified": bool(self.live_websocket_verified),
            "verification_note": (
                "wiring/session readiness is not business verification; verified flags"
                " become true only after a real endpoint succeeds"
            ),
            # Local payload/key/header pairing is not browser parity.  The
            # latter requires a capture that matched the JS AES hook to the
            # final wire header in the same invocation.
            "dtrait_byte_parity": (
                (self.dtrait_evidence() or {}).get("browser_wire_paired") is True
            ),
        }

    def dtrait_evidence(self):
        """Return the latest local dtrait material for byte-parity audits.

        This is diagnostic state only; the RSA private material is never
        exposed.  The AES key is included because a hook/capture must pair it
        with the exact final header and IV to prove ciphertext equality.
        """
        value = getattr(self, "_dtrait_last_evidence", None)
        return dict(value) if isinstance(value, dict) else None

    def bootstrap_creator_session(self, proxies=None):
        """模拟主域登录后进入 creator 页时的服务端/JS Cookie 初始化。

        保留 host-only 与 `.douyin.com` 同名 Cookie，不能再压平成一个 dict。
        """
        if self.creator_bootstrapped:
            return self
        from builder.header import HeaderBuilder
        from utils.dy_util import generate_s_v_web_id

        session = self.ensure_http_session()
        origin = "https://creator.douyin.com"
        referer = origin + "/creator-micro/content/upload"
        navigation_headers = {
            "sec-ch-ua-platform": HeaderBuilder.sec_ch_ua_platform,
            "upgrade-insecure-requests": "1",
            "user-agent": HeaderBuilder.ua,
            "accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8,"
                "application/signed-exchange;v=b3;q=0.7"
            ),
            "sec-ch-ua": HeaderBuilder.sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-fetch-site": "none",
            "sec-fetch-mode": "navigate",
            "sec-fetch-user": "?1",
            "sec-fetch-dest": "document",
            "accept-language": HeaderBuilder.accept_language,
            "priority": "u=0, i",
        }
        response = session.get(
            referer, headers=navigation_headers, verify=False, proxies=proxies,
        )
        response.raise_for_status()

        # Creator's first authenticated API fan-out contains one important
        # server-issued anonymous value that is not derivable from the CK:
        # ``odin_tt``.  Chromium receives it from the oversea judgment
        # endpoint (``Set-Cookie: odin_tt=...; Domain=.douyin.com``) and then
        # reuses it for subsequent creator/passport requests.  A plain CK may
        # legitimately omit this cookie, so perform the same read-only
        # bootstrap hop before constructing the creator cookie template.
        # Never synthesize a replacement; only an actual response can mark
        # the value as proven.
        oversea_headers = {
            "origin": origin,
            "accept": "*/*",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": referer,
            "user-agent": HeaderBuilder.ua,
            "accept-language": HeaderBuilder.accept_language,
        }
        try:
            oversea = session.get(
                origin + "/aweme/v1/web/oversea/judgment/",
                headers=oversea_headers, verify=False, proxies=proxies,
                timeout=20,
            )
            # curl_cffi's jar receives Set-Cookie automatically, but Auth's
            # flattened mapping and provenance ledger need the explicit merge.
            from utils.passport import merge_set_cookies
            merge_set_cookies(self, oversea.cookies.get_dict())
            if oversea.status_code >= 400:
                oversea.raise_for_status()
        except Exception:
            # This endpoint is a creator-side enrichment hop, not the login
            # credential itself.  Keep CK-only read/live usage available when
            # an edge omits it; publish/security checks still report whatever
            # material is actually present instead of fabricating odin_tt.
            pass

        host = "creator.douyin.com"
        # 页面脚本创建的 host-only Cookie；gd_random 由 document Set-Cookie 产生。
        # document 已写入 `.creator.douyin.com` 版本；浏览器随后由 secsdk 写成
        # host-only x-web-secsdk-uid，因此删掉前者，保留 `.douyin.com` 主域版本。
        for cookie in list(session.cookies.jar):
            if (cookie.name == "x-web-secsdk-uid"
                    and cookie.domain in {"creator.douyin.com", ".creator.douyin.com"}
                    and cookie.domain_specified):
                try:
                    session.cookies.jar.clear(cookie.domain, cookie.path, cookie.name)
                except KeyError:
                    pass
        self._set_host_only_cookie(host, "x-web-secsdk-uid", str(uuid.uuid4()))
        current_names = {cookie.name for cookie in session.cookies.jar}
        if "gfkadpd" not in current_names:
            session.cookies.set(
                "gfkadpd", "2906,33638", domain=".creator.douyin.com",
                path="/", secure=True,
            )
        if "_tea_utm_cache_2906" not in current_names:
            session.cookies.set(
                "_tea_utm_cache_2906", "undefined",
                domain=".creator.douyin.com", path="/", secure=True,
            )

        csrf_headers = {
            "x-secsdk-csrf-request": "1",
            "referer": referer,
            "user-agent": HeaderBuilder.ua,
            "x-secsdk-csrf-version": "1.2.22",
            "accept": "*/*",
            "accept-language": HeaderBuilder.accept_language,
        }
        csrf_response = session.head(
            origin + "/web/api/media/anchor/search",
            headers=csrf_headers, verify=False, proxies=proxies,
        )
        token_header = csrf_response.headers.get("X-Ware-Csrf-Token", "")
        parts = token_header.split(",")
        self.creator_csrf_token = parts[1] if len(parts) > 1 else ""
        self._set_host_only_cookie(host, "s_v_web_id", generate_s_v_web_id())
        self.creator_bootstrapped = True
        return self

    def close(self):
        if self.http is not None:
            self.http.close()
            self.http = None


    def ticket_matches_session(self):
        """校验 ts_sign 与当前 cookie 是否同属一次登录。

        cookie 里的 `bd_ticket_guard_ts_sign_id` 就是 ts_sign 的前缀。二者对不上
        说明 ticket 和 cookie 来自不同次登录，create_v2 这类强校验接口会直接失败，
        且报错信息（403 空响应 / status_code 4）完全看不出根因。提前拦下来报清楚。
        """
        if not self.ts_sign:
            return False
        sign_id = (self.cookie or {}).get("bd_ticket_guard_ts_sign_id")
        if not sign_id:
            return True  # 没有该 cookie 时无从判断，交给服务端
        return self.ts_sign.startswith(sign_id)

    def ecdh_key(self, aid=6383, origin="https://www.douyin.com"):
        """bd-ticket-guard HMAC 密钥（ECDH + HKDF），失败返回 None 由调用方回退 ECDSA。

        证书按 (aid, origin) 缓存：不同子域下发的 aid 不同，密钥不通用。
        """
        if not self.private_key:
            return None
        cache_key = (aid, origin)
        if cache_key in self._ecdh_cache:
            return self._ecdh_cache[cache_key]
        key = None
        try:
            from utils.bd_ticket import derive_ecdh_key, fetch_server_cert
            from builder.header import HeaderBuilder
            cert, _sn = fetch_server_cert(
                aid, self.cookie_str, origin=origin, user_agent=HeaderBuilder.ua,
            )
            self.server_cert = cert
            key = derive_ecdh_key(self.private_key, cert)
        except Exception:
            key = None
        self._ecdh_cache[cache_key] = key
        return key

    @property
    def webid(self):
        """真实设备号，取一次缓存复用。

        优先向 `/aweme/v1/web/query/user` 换取；该接口自身也要带 webid，
        引导阶段用随机值顶上（`_webid_resolving` 防递归）。
        退而求其次才去抓服务端渲染页面里的 `user_unique_id`。
        随机 webid 会被搜索等接口静默拒绝（HTTP 200 但响应体为空），所以务必拿到真值。
        """
        if self._webid:
            return self._webid
        if self._webid_resolving:
            from utils.dy_util import generate_fake_webid
            return generate_fake_webid()
        self._webid_resolving = True
        try:
            wid = douyin_api.DouyinAPI.get_device_id(self) or ""
        except Exception:
            wid = ""
        finally:
            self._webid_resolving = False
        if not wid:
            from utils.dy_util import generate_webid
            wid = generate_webid(self, "https://www.douyin.com/discover")
        self._webid = wid
        return self._webid

    def session_dtrait_header(self, path, aid=6383, origin="https://www.douyin.com",
                              timestamp=None, randbytes=None, strict=False,
                              allow_static=True):
        """按请求 path 生成 x-tt-session-dtrait；拿不到素材时返回 None。"""
        blob = self.dtrait_blob
        if not blob and self.dtrait_profile:
            try:
                from utils.dtrait_features import build_blob
                blob = build_blob(self.dtrait_profile)
            except Exception:
                blob = None
        # A captured complete header is safe only for non-strict legacy
        # callers.  Strict login/publish paths must rebuild the second AES
        # segment for the current pathname and therefore cannot reuse a
        # static whole header.
        if not blob and self.session_dtrait and allow_static and not strict:
            return self.session_dtrait
        if not blob:
            if strict:
                raise RuntimeError(
                    "缺少可按 path 重算的 dtrait 设备素材；请配置 DY_DTRAIT_BLOB "
                    "或使用内置 dtrait_profile，"
                    "发布接口禁止省略 x-tt-session-dtrait"
                )
            return None
        try:
            from utils.dtrait import (
                build_session_dtrait,
                builtin_trait_pubkey,
                fetch_trait_pubkey,
            )
            from builder.header import HeaderBuilder
            cache_key = (aid, origin)
            pk = self._trait_pk_cache.get(cache_key)
            if pk is None:
                # The browser's QR-login initialization uses the SDK's
                # embedded d0 certificate and therefore does not issue a
                # separate ``type=trait`` request before challenge.  Keep a
                # remote escape hatch for key rotation/debugging, but make
                # browser parity the default.
                cert_mode = os.getenv("DY_DTRAIT_CERT_MODE", "builtin").lower()
                if cert_mode in {"remote", "server", "fetch"}:
                    pk = fetch_trait_pubkey(
                        aid, self.cookie_str,
                        csrf_token=self.cookie.get('passport_csrf_token')
                        or self.cookie.get('passport_csrf_token_default') or '',
                        origin=origin, user_agent=HeaderBuilder.ua,
                    )
                else:
                    pk = builtin_trait_pubkey()
                # ticket_guard/get_client_cert also seeds passport CSRF
                # cookies.  Preserve them before the caller builds its next
                # passport request (notably the initial challenge).
                for name, value in (pk.get("_set_cookies") or {}).items():
                    if value:
                        self.cookie[name] = value
                self.cookie_str = "; ".join(
                    f"{k}={v}" for k, v in self.cookie.items())
                self._trait_pk_cache[cache_key] = pk
            fixed_timestamp = (
                timestamp if timestamp is not None
                else os.getenv("DY_DTRAIT_FIXED_TIMESTAMP")
            )
            effective_timestamp = (
                int(fixed_timestamp) if fixed_timestamp is not None
                else int(time.time())
            )
            sdk_version = (os.getenv("DY_DTRAIT_SDK_VERSION")
                           or "1.0.0.16")
            if randbytes is None:
                encoded = (os.getenv("DY_DTRAIT_FIXED_RANDBYTES") or "").strip()
                if encoded:
                    try:
                        raw = (bytes.fromhex(encoded) if len(encoded) % 2 == 0
                               else base64.b64decode(encoded + "=="))
                    except Exception as error:
                        raise ValueError(
                            "DY_DTRAIT_FIXED_RANDBYTES 必须是十六进制或 base64"
                        ) from error
                    cursor = 0

                    def fixed_randbytes(size):
                        nonlocal cursor
                        end = cursor + int(size)
                        if end > len(raw):
                            raise ValueError(
                                "DY_DTRAIT_FIXED_RANDBYTES 长度不足，无法完成 RSA/AES 随机流"
                            )
                        chunk = raw[cursor:end]
                        cursor = end
                        return chunk

                    randbytes = fixed_randbytes
            material_key = (
                int(aid), str(origin), hashlib.sha256(str(blob).encode("utf-8")).hexdigest(),
                str(pk.get("pk1_version") or ""),
            )
            material = self._dtrait_material_cache.get(material_key)
            if material is None:
                header, material = build_session_dtrait(
                    path, blob, pk["pk1"], pk["pk1_version"],
                    sdk_version=sdk_version,
                    timestamp=effective_timestamp,
                    randbytes=randbytes, return_material=True,
                )
                self._dtrait_material_cache[material_key] = material
                self._record_dtrait_evidence(path, blob, effective_timestamp,
                                              sdk_version, pk, header, material)
                return header
            header = build_session_dtrait(
                path, blob, pk["pk1"], pk["pk1_version"],
                sdk_version=sdk_version,
                timestamp=effective_timestamp,
                randbytes=randbytes, session_material=material,
            )
            self._record_dtrait_evidence(path, blob, effective_timestamp,
                                          sdk_version, pk, header, material)
            return header
        except Exception as error:
            if strict:
                raise RuntimeError(
                    f"x-tt-session-dtrait 构造失败: {error}"
                ) from error
            return None

    def _record_dtrait_evidence(self, path, blob, timestamp, sdk_version, pk,
                                header, material):
        """Capture exact AES inputs/outputs used for the latest header."""
        try:
            key_hex, enc_key = material
            parts = str(header).split("_")
            raw = base64.b64decode(parts[2] + "=" * (-len(parts[2]) % 4))
            iv, ciphertext = raw[:16], raw[16:]
            payload = {
                "dtrait": blob,
                "timestamp": int(timestamp if timestamp is not None else time.time()),
                "sdkVersion": sdk_version or "1.0.0.16",
                "path": path,
            }
            payload_json = json.dumps(payload, ensure_ascii=False,
                                      separators=(",", ":"))
            self._dtrait_last_evidence = {
                "evidence_source": "local_rebuild",
                "browser_wire_paired": False,
                "payload": payload_json,
                "aes_key_hex": key_hex,
                "iv": iv.hex(),
                "ciphertext": base64.b64encode(ciphertext).decode(),
                "cipherText": base64.b64encode(raw).decode(),
                "enc_key": base64.b64encode(enc_key).decode(),
                "header": header,
                "same_invocation": True,
                "path": path,
                "pk1_version": pk.get("pk1_version", ""),
            }
        except Exception:
            self._dtrait_last_evidence = None

    @property
    def msToken(self):
        """惰性获取 msToken：首次/过期时自动纯算换取真 token（绑定本会话 ttwid），失败回退随机。
        这样 search 等需要 msToken 的调用无需手动准备，缺失/过期会自动补上。"""
        now = time.time()
        if self._ms_cache and (self._ms_pinned or now - self._ms_ts < _MS_TTL):
            return self._ms_cache
        tok = ""
        try:
            tok = generate_dynamic_msToken(ttwid=self._ttwid)
        except Exception:
            tok = ""
        if tok:
            self._ms_cache = tok
            self._ms_ts = now
            return tok
        return self._ms_cache or generate_msToken()

    @msToken.setter
    def msToken(self, value):
        if value:
            self._ms_cache = value
            self._ms_ts = time.time()

    def refresh_mstoken(self, common=False, common_behavior=False, sms=False):
        """强制刷新 msToken（如遇接口因 token 过期报错时可调用）。"""
        if common:
            previous = self._ms_cache
            previous_ts = self._ms_ts
            try:
                from utils.mstoken import refresh_common_mstoken
                token = refresh_common_mstoken(
                    ttwid=self._ttwid, current_token=previous,
                    proxies=self._proxies, behavior=common_behavior, sms=sms,
                    cookie_sink=self._merge_runtime_cookies)
                if token:
                    self._ms_cache = token
                    self._ms_ts = time.time()
                    return token
            except Exception:
                pass
            # A QR-owned token must only rotate through /web/common.  Falling
            # back to /web/r/token here creates the wrong Chrome lifecycle and
            # was the original cause of scanned -> error_code=7.  Preserve the
            # last accepted token when common fails; callers may retry on the
            # next browser-timed common report.
            if previous:
                self._ms_cache = previous
                self._ms_ts = previous_ts
                return previous
            if self._ms_pinned:
                return ""
        self._ms_cache = ""
        self._ms_ts = 0
        return self.msToken

    def _merge_runtime_cookies(self, values):
        """Merge cookies emitted by SDK runtime endpoints.

        The sink receives a cookie mapping, not the original response header.
        Keep that distinction explicit: only ``merge_set_cookies`` (called
        with an actual HTTP response's Set-Cookie mapping) may mark a value as
        ``server_set_cookie``.  This sink remains unclassified so a future SDK
        cookie cannot be mistaken for proven server provenance.
        """
        if not values:
            return
        for name, value in dict(values).items():
            if value in (None, ""):
                continue
            self.cookie[name] = str(value)
            self.mark_cookie_source(
                name, "runtime_response_unclassified",
                detail="mssdk runtime cookie sink; original Set-Cookie header unavailable",
            )
        self.cookie_str = "; ".join(
            f"{name}={value}" for name, value in self.cookie.items())

    def get_uid(self):
        if self.uid is None:
            self.uid = douyin_api.DouyinAPI.get_my_uid(self)
        return self.uid
