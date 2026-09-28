# coding=utf-8
"""统一 HTTP 出口：用 curl_cffi 冒充 Chrome 的 TLS / HTTP2 指纹。

requests 走 Python 自己的 TLS 栈和 HTTP/1.1，JA3/JA4 指纹、HTTP/2 SETTINGS 帧、
ALPN 协商结果跟 Chrome 完全不是一回事。风控看这一层比看 header 字典顺序重得多，
header 对得再齐，TLS 握手一开口还是 Python。curl_cffi 底下是 curl-impersonate，
能把这层补上。

用法是 requests 的替代品，调用点不用改：

    from utils import http_client as requests
    requests.post(url, headers=..., cookies=..., data=..., verify=False)

两个刻意的选择：

1. `default_headers=False`：impersonate 默认会塞一整套 Chrome 默认头
   （含 sec-ch-ua / accept 等）。但抖音页面发的 XHR 并不带 sec-ch-ua*，
   HeaderBuilder 已经按实录裁剪过了，让 curl 再加回来就白改了。
   这里只要指纹，不要它的头。curl 按我们给的顺序发，顺序也就跟着对齐了。

2. 每次请求开一个新 session：curl_cffi 的 Session 会攒 Set-Cookie 并在后续请求
   自动带上，而本项目所有调用都显式传 `cookies=auth.cookie`，两者叠加容易出现
   「.env 里的 cookie 被响应里的旧值盖掉」这种极难排查的问题。保持和原来
   requests 模块级函数一致的语义：一次请求一个连接，互不串味。
"""

from curl_cffi import requests as _cffi
from curl_cffi.requests.headers import Headers as _Headers
from curl_cffi.requests.models import Request as _Request
from curl_cffi.requests.models import Response as _Response
from contextlib import contextmanager
import os
import re
import threading


def _resolve_impersonate():
    """Pick the newest profile actually shipped by the installed curl_cffi.

    Chrome 151 is the browser-side UA in the current capture, but curl_cffi
    0.16.x only ships transport profiles through chrome150.  Passing the
    unsupported name makes every request fail before a socket is opened.
    Keep an explicit environment override, use the closest supported Chrome
    profile when possible, and let a newer curl_cffi use chrome151
    automatically once it becomes available.
    """
    requested = (os.getenv("DY_HTTP_IMPERSONATE") or "chrome151").strip().lower()
    try:
        from curl_cffi.requests.impersonate import BrowserType
        supported = {item.value for item in BrowserType}
    except Exception:
        supported = set()
    if not supported or requested in supported:
        return requested
    match = re.fullmatch(r"chrome(\d+)", requested)
    if match:
        wanted = int(match.group(1))
        candidates = sorted(
            int(value[6:]) for value in supported
            if re.fullmatch(r"chrome\d+", value)
            and int(value[6:]) <= wanted
        )
        if candidates:
            return f"chrome{candidates[-1]}"
    return "chrome" if "chrome" in supported else "chrome150"


# This is the transport profile, not the HTTP User-Agent string.  With the
# currently installed curl_cffi it resolves chrome151 -> chrome150; upgrading
# curl_cffi to a build that contains chrome151 makes the same code exact.
IMPERSONATE = _resolve_impersonate()

DEFAULT_TIMEOUT = 30


def _resolve_http_version():
    """Return the transport protocol used by the browser baseline.

    Passport/creator XHR captures from Chrome negotiate HTTP/2 over TLS.  Do
    not leave this to libcurl's default negotiation: an intermediary or a
    future curl_cffi release may fall back to HTTP/1.1, which changes both the
    pseudo-header framing and Cookie crumbling.  Keep an explicit escape hatch
    for diagnostics, but use HTTP/2 by default.
    """
    value = (os.getenv("DY_HTTP_VERSION") or "v2").strip().lower()
    return value or "v2"


HTTP_VERSION = _resolve_http_version()


def split_h2_cookie_fields(cookie_header):
    """按 Chromium HTTP/2 wire 形式拆成独立 ``cookie`` 字段值。"""
    return [part.strip() for part in str(cookie_header or "").split(";")
            if part.strip()]


def request(method, url, **kwargs) -> _Response:
    # Compatibility bridge for the many historical API call sites that pass
    # ``cookies=auth.cookie`` to this module.  CookieDict carries a private
    # owner back-reference, so those calls now use the same persistent Auth
    # Session (TLS handle, connection pool and Set-Cookie lifecycle) without
    # duplicating every endpoint implementation.
    cookie_arg = kwargs.get("cookies")
    owner = getattr(cookie_arg, "_auth_owner", None)
    if owner is not None and hasattr(owner, "request"):
        return owner.request(method, url, **kwargs)
    kwargs.setdefault("impersonate", IMPERSONATE)
    kwargs.setdefault("default_headers", False)
    kwargs.setdefault("http_version", HTTP_VERSION)
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return _cffi.request(method, url, **kwargs)


class Session:
    """持久 Chrome 指纹会话，用于需要 Cookie jar/连接复用的登录与 creator 链。"""

    def __init__(self):
        self._session = _cffi.Session()
        # curl_cffi Session/CookieJar is not safe for concurrent mutation.  In
        # particular request_with_cookie_header() temporarily empties the jar
        # to preserve Chromium's explicit Cookie wire position.  Creator cover
        # polling and the main publish flow run in parallel, so every access to
        # the persistent handle must share one re-entrant critical section.
        self._lock = threading.RLock()

    @contextmanager
    def locked(self):
        with self._lock:
            yield self

    @property
    def cookies(self):
        return self._session.cookies

    def request(self, method, url, **kwargs) -> _Response:
        kwargs.setdefault("impersonate", IMPERSONATE)
        kwargs.setdefault("default_headers", False)
        kwargs.setdefault("http_version", HTTP_VERSION)
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        with self._lock:
            return self._session.request(method, url, **kwargs)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)

    def head(self, url, **kwargs):
        return self.request("HEAD", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)

    def close(self):
        with self._lock:
            self._session.close()

    def cookie_header(self, url, method="GET"):
        with self._lock:
            morsels = self.cookies.get_cookies_for_curl(
                _Request(url=url, headers=_Headers(), method=method),
            )
            return "; ".join(f"{item.name}={item.value}" for item in morsels)

    def request_with_cookie_header(self, method, url, cookie_header, **kwargs):
        """显式发送 Cookie，同时保留持久 jar 的 Set-Cookie 生命周期。

        ``split_cookie_header=True`` 时把每个 Cookie pair 作为一条独立的
        HTTP/2 ``cookie`` 字段发送。Chromium 会做这种 cookie crumbling；
        把整串合成一条虽然语义等价，但 wire 数量和每条长度都不一致。
        """
        with self._lock:
            on_fresh_cookies = kwargs.pop("on_fresh_cookies", None)
            old = list(self.cookies.jar)
            self.cookies.clear()
            split_cookie_header = bool(kwargs.pop("split_cookie_header", False))
            headers = dict(kwargs.pop("headers", {}) or {})
            # 调用方若已把 Cookie 放进精确 wire 位置，不得删除后再追加到末尾。
            if not any(name.lower() == "cookie" for name in headers):
                headers["cookie"] = cookie_header
            wire_headers = headers
            if split_cookie_header:
                wire_headers = []
                for name, value in headers.items():
                    if name.lower() == "cookie":
                        wire_headers.extend(
                            (name, field) for field in split_h2_cookie_fields(value)
                        )
                    else:
                        wire_headers.append((name, value))
            try:
                response = self.request(method, url, headers=wire_headers, **kwargs)
                fresh = list(self.cookies.jar)
            finally:
                # 即使请求异常也先恢复旧 jar；fresh 仅在拿到响应时存在。
                self.cookies.clear()
                for cookie in old:
                    self.cookies.jar.set_cookie(cookie)
            for cookie in locals().get("fresh", []):
                self.cookies.jar.set_cookie(cookie)
            if on_fresh_cookies is not None:
                on_fresh_cookies(list(locals().get("fresh", [])))
            return response


def get(url, **kwargs):
    return request("GET", url, **kwargs)


def post(url, **kwargs):
    return request("POST", url, **kwargs)


def put(url, **kwargs):
    return request("PUT", url, **kwargs)


def head(url, **kwargs):
    return request("HEAD", url, **kwargs)


def delete(url, **kwargs):
    return request("DELETE", url, **kwargs)


class _Urllib3Shim:
    """`requests.packages.urllib3.disable_warnings()` 的空壳。

    curl_cffi 不走 urllib3，也不会打 InsecureRequestWarning，
    留这个只是为了让原有调用点不用删。
    """

    @staticmethod
    def disable_warnings(*args, **kwargs):
        return None


class _PackagesShim:
    urllib3 = _Urllib3Shim


packages = _PackagesShim
exceptions = _cffi.exceptions
