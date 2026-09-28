# -*- coding: utf-8 -*-
"""抖音登录（纯算，不依赖浏览器自动化）。

两种方式：

- **扫码登录**：`qrcode_login()`。取二维码 -> 展示 -> 轮询状态 -> 成功后跟随
  重定向落 Cookie。
- **短信验证码登录**：`phone_login()`。手机号与验证码按 passport 的
  `XOR 5 + hex` 加密（见 `utils/passport.py`）。

登录过程中会自己生成一对 P-256 密钥并在请求头带上公钥，登录响应里服务端会通过
`bd-ticket-guard-server-data` 下发 `ticket` / `ts_sign` / `client_cert`，
解出来写回 auth 即可，无需读浏览器 localStorage。
"""

import base64
import datetime
import hashlib
import hmac
import json
import os
import random
import re
import secrets
import time
import urllib.parse
import uuid

from utils import http_client as requests
requests.packages.urllib3.disable_warnings()
from loguru import logger

from builder.auth import DouyinAuth
from builder.header import Header, HeaderBuilder, HeaderType
from builder.params import Params
from utils.dy_util import generate_a_bogus, generate_s_v_web_id, CookieDict, bind_cookie_owner
from utils.fingerprint import build_fpk1, build_fpk2, get_profile
from utils.passport import (CLIENT_DATA_COOKIE, CLIENT_WEB_DOMAIN_COOKIE,
                           apply_ticket_guard, build_client_data_cookie,
                           build_client_data_v2_cookie, merge_set_cookies,
                           generate_ec_keypair, passport_encrypt)

CLIENT_DATA_V2_COOKIE = "bd_ticket_guard_client_data_v2"

# ---- Cookie 的域作用域 ----
# 浏览器按 domain 属性决定发哪些 Cookie，我们却是把整个 jar 无差别发给所有域。
# 2026-08-22 实录对比（同一次登录里两个域各发了什么）：
#
#   www.douyin.com   : ... s_v_web_id / __ac_nonce / __ac_signature /
#                      x-web-secsdk-uid / dy_swidth / dy_sheight ...
#   login.douyin.com : 上面这些**一个都没有**
#
# 说明它们是 host-only（domain 就是 www.douyin.com），不会带到 login 子域。
# 这几个名字必须在发往 login.douyin.com 时剔掉。
WWW_ONLY_COOKIES = ("s_v_web_id", "__ac_nonce", "__ac_signature",
                    "x-web-secsdk-uid", "dy_swidth", "dy_sheight",
                    "device_web_cpu_core", "device_web_memory_size",
                    "architecture", "fpk1", "fpk2")
LOGIN_EXCLUDED_COOKIES = ("my_rd",)

# login.douyin.com 上的 Cookie 顺序，逐项照实录。
# 顺序本身也是指纹：浏览器按「写入时间」排；请求发送时必须走
# ``headers_with_cookie``，不能把这个 mapping 交给 curl_cffi 的 Cookie Jar。
LOGIN_COOKIE_ORDER = (
    "enter_pc_once", "UIFID_TEMP", "is_support_rtm_web_ts", "hevc_supported",
    "IsDouyinActive", "home_can_add_dy_2_desktop",
    "stream_recommend_feed_params", "odin_tt", "strategyABtestKey",
    "passport_csrf_token", "passport_csrf_token_default", "ttwid",
    "__security_mc_1_s_sdk_crypt_sdk", "bd_ticket_guard_regenerate_keys_time",
    "bd_ticket_guard_client_data", "bd_ticket_guard_client_web_domain",
    "bd_ticket_guard_client_data_v2", "biz_trace_id", "sdk_source_info", "bit_env",
    "gulu_source_res", "passport_auth_mix_state",
)

# Chrome 151's phone-code flow uses a different write/serialization order from
# the QR flow.  Keep the two requests explicit: the live send_code request
# (reqid=1765) carried 26 pairs, including the page's MONITOR_WEB_ID/UIFID and
# download_guide.  This order is the exact Cookie header order, not dict order.
SMS_COOKIE_ORDER = (
    "enter_pc_once", "UIFID_TEMP", "is_support_rtm_web_ts", "hevc_supported",
    "home_can_add_dy_2_desktop", "odin_tt", "strategyABtestKey", "is_dash_user",
    "passport_csrf_token", "passport_csrf_token_default",
    "__security_mc_1_s_sdk_crypt_sdk", "bd_ticket_guard_regenerate_keys_time",
    "bd_ticket_guard_client_web_domain", "download_guide", "MONITOR_WEB_ID",
    "UIFID", "IsDouyinActive", "stream_recommend_feed_params", "ttwid",
    "biz_trace_id", "bd_ticket_guard_client_data", "bd_ticket_guard_client_data_v2",
    "sdk_source_info", "bit_env", "gulu_source_res", "passport_auth_mix_state",
)

# After the code is submitted Chrome rewrites only the tail placement of
# download_guide.  The live sms_login request (reqid=1874) carried the same
# 26 names but serialized download_guide last.  Keep this separate from the
# send_code order; collapsing them changes the Cookie bytes.
SMS_LOGIN_REFRESH_COOKIE_ORDER = (
    "enter_pc_once", "UIFID_TEMP", "is_support_rtm_web_ts", "hevc_supported",
    "home_can_add_dy_2_desktop", "odin_tt", "strategyABtestKey", "is_dash_user",
    "passport_csrf_token", "passport_csrf_token_default",
    "__security_mc_1_s_sdk_crypt_sdk", "bd_ticket_guard_regenerate_keys_time",
    "bd_ticket_guard_client_web_domain", "MONITOR_WEB_ID", "UIFID",
    "IsDouyinActive", "stream_recommend_feed_params", "ttwid", "biz_trace_id",
    "bd_ticket_guard_client_data", "bd_ticket_guard_client_data_v2",
    "sdk_source_info", "bit_env", "gulu_source_res", "passport_auth_mix_state",
    "download_guide",
)

# Fresh Chrome 151 jingxuan SMS request captured on 2026-08-29 (reqid=558).
# This is a different page lifecycle from the older 26-pair fixture above:
# the first phone-code request is sent before the page writes
# MONITOR_WEB_ID/UIFID/download_guide.  Keep this vector explicit instead of
# padding it with values from a later/expired challenge window.
SMS_CURRENT_COOKIE_ORDER = (
    "enter_pc_once", "UIFID_TEMP", "odin_tt", "is_support_rtm_web_ts",
    "hevc_supported", "IsDouyinActive", "home_can_add_dy_2_desktop",
    "stream_recommend_feed_params", "strategyABtestKey", "is_dash_user",
    "passport_csrf_token", "passport_csrf_token_default", "ttwid",
    "biz_trace_id", "__security_mc_1_s_sdk_crypt_sdk",
    "bd_ticket_guard_regenerate_keys_time", "bd_ticket_guard_client_data",
    "bd_ticket_guard_client_web_domain", "bd_ticket_guard_client_data_v2",
    "sdk_source_info", "bit_env", "gulu_source_res",
    "passport_auth_mix_state",
)

SMS_CURRENT_COOKIE_LENGTH = 3280
SMS_HISTORICAL_ONLY_COOKIES = frozenset(
    ("MONITOR_WEB_ID", "UIFID", "download_guide")
)

# These values are opaque session material.  A matching length/charset is
# useful for wire-shape diagnostics, but is not evidence of a local generator.
# Keep the accepted provenance explicit so strict flows cannot silently fall
# back to random placeholders. ``passport_auth_mix_state`` is the exception:
# its random length/alphabet generator is fully recovered.
ANONYMOUS_OPAQUE_COOKIES = (
    "UIFID_TEMP", "odin_tt", "bit_env", "passport_auth_mix_state",
)
ANONYMOUS_COOKIE_LENGTHS = {
    "UIFID_TEMP": {"modern": 224, "legacy": 160},
    # Browser captures contain three valid lifecycle shapes for this server-
    # issued value (96/128/160).  The strict SMS wire profiles below still
    # require the exact 160-byte vector; this wider diagnostic set prevents a
    # pasted CK from being mislabeled UNPROVEN merely because it came from a
    # different page/session lifecycle.
    "odin_tt": {
        "modern": 160, "legacy": 160,
        "historical_96": 96, "historical_128": 128,
    },
    "bit_env": {"modern": 512, "legacy": 512},
    "passport_auth_mix_state": {
        "modern": 48, "current_23": 48,
        "historical_26": 32, "legacy": 32,
    },
}
ANONYMOUS_ACCEPTED_SOURCES = frozenset(
    # ``node_page_js`` means the shipped acrawler VMP was executed in the
    # page-shaped Node realm (no Chrome process).  It is accepted only for
    # fields the runner actually computes, notably ``__ac_signature``.
    ("captured_input", "server_set_cookie", "browser_runtime", "node_page_js",
     "local_pure_conditional"))
# Provenance is field-specific. A local derivation consuming challenge
# ``passportiv`` is valid for ``bit_env`` only; ``local_pure_random`` is
# allowed only for the independently recovered mix-state generator.
ANONYMOUS_ACCEPTED_SOURCES_BY_FIELD = {
    "UIFID_TEMP": frozenset(("captured_input", "server_set_cookie",
                              "browser_runtime")),
    "odin_tt": frozenset(("captured_input", "server_set_cookie",
                           "browser_runtime")),
    "bit_env": ANONYMOUS_ACCEPTED_SOURCES,
    "passport_auth_mix_state": frozenset(("captured_input", "server_set_cookie",
                                           "browser_runtime", "local_pure_random")),
    "__ac_nonce": frozenset(("captured_input", "server_set_cookie",
                              "browser_runtime")),
    "__ac_signature": frozenset(("captured_input", "browser_runtime",
                                  "node_page_js")),
}
_MIX_STATE_ALPHABET = "1234567890qwertyuiopasdfghjklzxcvbnm"


def generate_passport_auth_mix_state(length=None, *, rng=None):
    """Reproduce the page SDK's *rule* for ``passport_auth_mix_state``.

    The shipped bundle uses ``16 * (floor(Math.random() * 4) + 1)`` and then
    samples the lowercase-alphanumeric alphabet.  This is a complete local
    generator. It will not equal the bytes from a different browser call;
    historical byte equality still requires that call's captured value or a
    replayed ``Math.random`` trace.
    """
    chooser = rng or random.random
    if length is None:
        length = 16 * (int(chooser() * 4) + 1)
    length = int(length)
    if length < 16 or length % 16:
        raise ValueError("passport_auth_mix_state length must be a positive multiple of 16")
    pick = rng or random.random
    return "".join(_MIX_STATE_ALPHABET[int(pick() * len(_MIX_STATE_ALPHABET))]
                   for _ in range(length))


def _anonymous_cookie_report(auth):
    """Return evidence status for opaque anonymous Cookie fields.

    ``proven`` means only that this concrete value was observed (from input,
    Set-Cookie, or a browser runtime handoff) and has the captured shape.  It
    intentionally does *not* claim that a deterministic local generation rule
    has been recovered.
    """
    cookie = getattr(auth, "cookie", None) or {}
    profile = _passport_profile("DY_PASSPORT_COOKIE_PROFILE")
    modern = profile in ("chrome_current", "chrome_current_early")
    sms_profile = _sms_cookie_profile(auth)
    expected_profile = sms_profile if getattr(auth, "phone_login_profile", "") == "passport_web" \
        else ("modern" if modern else "legacy")
    result = {}
    for name in ANONYMOUS_OPAQUE_COOKIES:
        value = cookie.get(name)
        source = (auth.cookie_source(name)
                  if hasattr(auth, "cookie_source") else "unknown")
        length = len(str(value or ""))
        expected = ANONYMOUS_COOKIE_LENGTHS[name].get(expected_profile)
        if expected is None:
            expected = ANONYMOUS_COOKIE_LENGTHS[name].get(
                "modern" if modern else "legacy")
        # Browser captures show profile drift (notably UIFID_TEMP 160 vs 224
        # and mix-state 32 vs 48).  Keep the profile-specific expectation for
        # diagnostics, but accept any length that has been independently
        # observed for this field; provenance remains the decisive gate.
        observed_lengths = {
            int(item) for item in ANONYMOUS_COOKIE_LENGTHS[name].values()
            if isinstance(item, int)
        }
        shape_ok = bool(value) and (not observed_lengths or length in observed_lengths)
        # Values generated by the old fallback are deliberately not accepted
        # as proof, even when shape_ok is true.
        source_ok = source in ANONYMOUS_ACCEPTED_SOURCES_BY_FIELD.get(
            name, ANONYMOUS_ACCEPTED_SOURCES)
        result[name] = {
            "present": bool(value), "length": length,
            "expected_length": expected, "accepted_lengths": sorted(observed_lengths),
            "source": source,
            "shape_ok": shape_ok, "source_ok": source_ok,
            "status": "PROVEN_OBSERVED" if shape_ok and source_ok
            else ("UNPROVEN" if value else "MISSING"),
        }
    return result


def anonymous_cookie_evidence(auth):
    """Public JSON-safe evidence report for anonymous Cookie fields."""
    return _anonymous_cookie_report(auth)


def _assert_anonymous_cookie_evidence(auth, *, context="passport",
                                      required_names=None):
    report = _anonymous_cookie_report(auth)
    required = set(required_names or report)
    bad = [
        f"{name}={item['status']} source={item['source']} len={item['length']}"
        for name, item in report.items()
        if name in required
        if item["status"] != "PROVEN_OBSERVED"
    ]
    if bad:
        raise RuntimeError(
            f"严格 {context} 要求匿名 Cookie 有捕获/Set-Cookie/浏览器运行时证据；"
            "长度正确的随机占位值不算证明：" + "; ".join(bad)
        )
    return report


def _sms_cookie_profile(auth=None):
    """Select only a browser-observed SMS Cookie lifecycle.

    ``current_23`` is the default for a fresh jingxuan session and is backed
    by the live reqid=558 capture.  ``historical_26`` is opt-in for the older
    delayed-submit capture where Chrome had already written
    MONITOR_WEB_ID/UIFID/download_guide.  Presence of those three values in a
    caller-supplied browser jar also selects that observed profile; no value
    is synthesized to force the selection.
    """
    value = (os.getenv("DY_SMS_COOKIE_PROFILE") or "").strip().lower()
    aliases = {
        "current": "current_23", "chrome_current": "current_23",
        "fresh": "current_23", "fresh_23": "current_23",
        "historical": "historical_26", "legacy": "historical_26",
        "chrome_historical": "historical_26", "old": "historical_26",
    }
    value = aliases.get(value, value)
    if value in {"current_23", "historical_26"}:
        return value
    jar = getattr(auth, "cookie", None) or {}
    if any(jar.get(name) not in (None, "")
           for name in ("MONITOR_WEB_ID", "UIFID", "download_guide")):
        return "historical_26"
    return "current_23"

# QR bootstrap requests have a distinct browser jar.  In particular Chrome
# does not send client_data_v2 on the first challenge/get_qrcode/check cycle;
# that cookie may appear only after a later page-side ticket refresh.  The
# insertion order also follows the wire Cookie header from Chrome 151.
# Chrome 151 wire order from the user's live get_qrcode/check_qrconnect curl.
# `download_guide` is not present in that jar and must not be invented.  The
# v2 ticket-guard cookie is sent before sdk_source_info on the QR requests.
QR_COOKIE_ORDER = (
    "enter_pc_once", "UIFID_TEMP", "is_support_rtm_web_ts", "hevc_supported",
    "IsDouyinActive", "home_can_add_dy_2_desktop",
    "stream_recommend_feed_params", "odin_tt", "strategyABtestKey", "ttwid",
    "passport_csrf_token", "passport_csrf_token_default", "biz_trace_id",
    "__security_mc_1_s_sdk_crypt_sdk", "bd_ticket_guard_regenerate_keys_time",
    "bd_ticket_guard_client_data", "bd_ticket_guard_client_web_domain",
    "bd_ticket_guard_client_data_v2", "sdk_source_info", "bit_env",
    "gulu_source_res", "passport_auth_mix_state",
)

# A later Chrome 151 capture (reqid=4468) came from a page that had already
# initialized the main-site security SDK.  Its QR/check jar is intentionally
# different from the older pasted cURL: three extra page cookies are present
# and the write order is different.  Keep this as an explicit opt-in profile
# instead of silently changing the legacy fixture that is already verified
# byte-for-byte.  Values still come from the caller's cookie_str; we never
# read or copy browser cookies implicitly.
CHROME4468_QR_COOKIE_ORDER = (
    "enter_pc_once", "UIFID_TEMP", "odin_tt", "is_support_rtm_web_ts",
    "hevc_supported", "home_can_add_dy_2_desktop",
    "stream_recommend_feed_params", "is_dash_user",
    "passport_csrf_token", "passport_csrf_token_default",
    "__security_mc_1_s_sdk_crypt_sdk", "bd_ticket_guard_regenerate_keys_time",
    "bd_ticket_guard_client_web_domain", "UIFID", "strategyABtestKey",
    "download_guide", "gulu_source_res", "IsDouyinActive", "ttwid",
    "biz_trace_id", "bd_ticket_guard_client_data",
    "bd_ticket_guard_client_data_v2", "sdk_source_info", "bit_env",
    "passport_auth_mix_state",
)

# Fresh isolated Chrome 151 run (2026-08-23).  The page has ticket-guard
# client data before the first passport call, but it writes the v2 cookie only
# after a later QR refresh: challenge has 17 cookies, the first QR/check cycle
# has 21, and subsequent requests have 22.  Keep this lifecycle explicit so
# it can be reproduced without changing the legacy cURL or reqid=4468 profile.
CHROME_CURRENT_CHALLENGE_COOKIE_ORDER = (
    # 2026-08-29 live Chrome (reqid=492): the page SDK writes the
    # high-entropy odin/is_dash cookies and ticket-guard bootstrap cookies
    # before the passport challenge.
    "enter_pc_once", "UIFID_TEMP", "odin_tt", "is_support_rtm_web_ts",
    "hevc_supported", "IsDouyinActive", "home_can_add_dy_2_desktop",
    "stream_recommend_feed_params", "strategyABtestKey", "is_dash_user",
    "passport_csrf_token", "passport_csrf_token_default", "ttwid", "biz_trace_id",
    "__security_mc_1_s_sdk_crypt_sdk", "bd_ticket_guard_regenerate_keys_time",
    "bd_ticket_guard_client_data", "bd_ticket_guard_client_web_domain",
)
CHROME_CURRENT_QR_COOKIE_ORDER = (
    # 2026-08-29 live Chrome (reqid=438).
    "enter_pc_once", "UIFID_TEMP", "odin_tt", "is_support_rtm_web_ts",
    "hevc_supported", "IsDouyinActive", "home_can_add_dy_2_desktop",
    "stream_recommend_feed_params", "strategyABtestKey", "is_dash_user",
    "passport_csrf_token", "passport_csrf_token_default", "ttwid", "biz_trace_id",
    "__security_mc_1_s_sdk_crypt_sdk", "bd_ticket_guard_regenerate_keys_time",
    "bd_ticket_guard_client_data", "bd_ticket_guard_client_web_domain",
    "bd_ticket_guard_client_data_v2", "sdk_source_info", "bit_env",
    "gulu_source_res", "passport_auth_mix_state",
)
# After the first QR has expired, Chrome 151 refreshes the QR through a
# second get_qrcode request.  That request has the page's download_guide
# cookie, and its insertion order is not simply the first order with one item
# appended: gulu_source_res/download_guide are written before sdk_source_info
# and bit_env.  Keep the post-expiry jar explicit.
CHROME_CURRENT_QR_REFRESH_COOKIE_ORDER = (
    # 2026-08-29 live Chrome (reqid=733), after the first QR expires.
    "enter_pc_once", "UIFID_TEMP", "odin_tt", "is_support_rtm_web_ts",
    "hevc_supported", "IsDouyinActive", "home_can_add_dy_2_desktop",
    "stream_recommend_feed_params", "strategyABtestKey", "is_dash_user",
    "passport_csrf_token", "passport_csrf_token_default", "ttwid", "biz_trace_id",
    "__security_mc_1_s_sdk_crypt_sdk", "bd_ticket_guard_regenerate_keys_time",
    "bd_ticket_guard_client_data", "bd_ticket_guard_client_web_domain",
    "bd_ticket_guard_client_data_v2", "gulu_source_res", "download_guide",
    "sdk_source_info", "bit_env", "passport_auth_mix_state",
)

# A fresh Chrome profile can race the ticket-guard bootstrap differently: the
# first challenge goes out before the page SDK cookies, get_qrcode carries the
# four SDK cookies, and the first check appends the five ticket-guard cookies.
# This is a separate opt-in lifecycle (``chrome_current_early``), not a
# replacement for the already verified ``chrome_current`` profile.
CHROME_EARLY_CHALLENGE_COOKIE_ORDER = (
    "enter_pc_once", "UIFID_TEMP", "is_support_rtm_web_ts", "hevc_supported",
    "IsDouyinActive", "stream_recommend_feed_params", "odin_tt",
    "home_can_add_dy_2_desktop", "strategyABtestKey", "passport_csrf_token",
    "passport_csrf_token_default", "ttwid", "biz_trace_id",
)
CHROME_EARLY_QR_COOKIE_ORDER = CHROME_EARLY_CHALLENGE_COOKIE_ORDER + (
    "sdk_source_info", "bit_env", "gulu_source_res", "passport_auth_mix_state",
)
CHROME_EARLY_CHECK_COOKIE_ORDER = CHROME_EARLY_QR_COOKIE_ORDER + (
    "__security_mc_1_s_sdk_crypt_sdk", "bd_ticket_guard_regenerate_keys_time",
    "bd_ticket_guard_client_data", "bd_ticket_guard_client_web_domain",
    "bd_ticket_guard_client_data_v2",
)
CHROME_EARLY_REFRESH_COOKIE_ORDER = (
    # 2026-08-23 live Chrome, after the first QR expiry.  The page rewrites
    # the late SDK cookies, so this is not CHECK_ORDER + download_guide:
    # gulu moves ahead of ticket-guard, download_guide lands after v2, and
    # sdk_source_info/bit_env/mix_state are serialized last.
    "enter_pc_once", "UIFID_TEMP", "is_support_rtm_web_ts", "hevc_supported",
    "IsDouyinActive", "stream_recommend_feed_params", "odin_tt",
    "home_can_add_dy_2_desktop", "strategyABtestKey", "passport_csrf_token",
    "passport_csrf_token_default", "ttwid", "biz_trace_id",
    "gulu_source_res", "__security_mc_1_s_sdk_crypt_sdk",
    "bd_ticket_guard_regenerate_keys_time", "bd_ticket_guard_client_data",
    "bd_ticket_guard_client_web_domain", "bd_ticket_guard_client_data_v2",
    "download_guide", "sdk_source_info", "bit_env", "passport_auth_mix_state",
)

# www.douyin.com 上的顺序（get_sec_ts 实录）
WWW_COOKIE_ORDER = (
    "__ac_nonce", "__ac_signature", "ttwid", "enter_pc_once", "UIFID_TEMP",
    "x-web-secsdk-uid", "s_v_web_id", "is_support_rtm_web_ts", "hevc_supported",
    "IsDouyinActive", "home_can_add_dy_2_desktop",
    "dy_swidth", "dy_sheight", "stream_recommend_feed_params", "odin_tt",
)


# challenge（首个 passport 请求）时浏览器只有这 13 个 Cookie。
# bd_ticket_guard_* / sdk_source_info / gulu_source_res / passport_auth_mix_state
# 这些是**登录页 SDK 在 challenge 之后才写的**，那一刻还不存在。
# 早发等于时序不对：一个刚打开页面的浏览器不可能已经有它们。
CHALLENGE_COOKIE_ORDER = (
    "enter_pc_once", "UIFID_TEMP", "is_support_rtm_web_ts", "hevc_supported",
    "stream_recommend_feed_params", "odin_tt", "home_can_add_dy_2_desktop",
    "IsDouyinActive", "strategyABtestKey",
    "passport_csrf_token", "passport_csrf_token_default", "ttwid",
    "biz_trace_id",
)

# These two early-page requests use narrower jars than the later passport
# calls.  Keeping them explicit prevents client-data/template cookies created
# by our bootstrap from leaking into requests where Chrome has not sent them.
TTWID_COOKIE_ORDER = (
    # 2026-08-29 Chrome reqid=389, exact wire order (14 pairs).
    "enter_pc_once", "UIFID_TEMP", "odin_tt", "is_support_rtm_web_ts",
    "hevc_supported", "IsDouyinActive", "home_can_add_dy_2_desktop",
    "stream_recommend_feed_params", "strategyABtestKey", "ttwid",
    "is_dash_user", "biz_trace_id", "passport_csrf_token",
    "passport_csrf_token_default",
)
WWW_BOOTSTRAP_COOKIE_ORDER = (
    "__ac_nonce", "__ac_signature", "enter_pc_once", "UIFID_TEMP",
    # 2026-08-29 Chrome reqid=373, exact www bootstrap jar (24 pairs).
    "x-web-secsdk-uid", "s_v_web_id", "odin_tt", "douyin.com",
    "device_web_cpu_core", "device_web_memory_size", "architecture",
    "is_support_rtm_web_ts", "hevc_supported", "IsDouyinActive",
    "home_can_add_dy_2_desktop", "dy_swidth", "dy_sheight",
    "stream_recommend_feed_params", "strategyABtestKey", "ttwid",
    "is_dash_user", "biz_trace_id", "passport_csrf_token",
    "passport_csrf_token_default",
)

# The very first www/ttwid/check request happens before the passport guiding
# strategy response writes CSRF cookies.  Chrome 151 therefore sends the
# 20-pair page jar below, not the later 24-pair get_sec_ts jar.
WWW_TTWID_COOKIE_ORDER = (
    "__ac_nonce", "__ac_signature", "ttwid", "enter_pc_once", "UIFID_TEMP",
    "x-web-secsdk-uid", "s_v_web_id", "odin_tt", "douyin.com",
    "device_web_cpu_core", "device_web_memory_size", "architecture",
    "is_support_rtm_web_ts", "hevc_supported", "IsDouyinActive",
    "home_can_add_dy_2_desktop", "dy_swidth", "dy_sheight",
    "stream_recommend_feed_params", "strategyABtestKey",
)

# login_guiding_strategy runs after www/ttwid/check and before get_sec_ts.
# Its jar includes the page/device state and the newly accepted ttwid, but no
# CSRF pair yet; those arrive in this response's Set-Cookie headers.
WWW_GUIDING_COOKIE_ORDER = (
    "__ac_nonce", "__ac_signature", "enter_pc_once", "UIFID_TEMP",
    "x-web-secsdk-uid", "s_v_web_id", "odin_tt", "douyin.com",
    "device_web_cpu_core", "device_web_memory_size", "architecture",
    "is_support_rtm_web_ts", "hevc_supported", "IsDouyinActive",
    "home_can_add_dy_2_desktop", "dy_swidth", "dy_sheight",
    "stream_recommend_feed_params", "strategyABtestKey", "ttwid",
    "is_dash_user", "biz_trace_id",
)

# `ticket_guard/get_client_cert` is a www.douyin.com request, not a passport
# request. Chrome sends the page/security cookies first, then the passport SDK
# cookies written later in the same tab. Keep this separate from
# WWW_BOOTSTRAP_COOKIE_ORDER (used by get_sec_ts), because both the set and
# the wire order differ.
TICKET_GUARD_COOKIE_ORDER = (
    # 2026-08-29 Chrome reqid=494, exact early ticket-guard jar (28 pairs).
    # ``douyin.com`` is a legacy bare token shown by DevTools without an
    # equals sign; it is kept in this position by the raw-token sidecar.
    "__ac_nonce", "__ac_signature", "enter_pc_once", "UIFID_TEMP",
    "x-web-secsdk-uid", "s_v_web_id", "odin_tt", "douyin.com",
    "device_web_cpu_core", "device_web_memory_size", "architecture",
    "is_support_rtm_web_ts", "hevc_supported", "IsDouyinActive",
    "home_can_add_dy_2_desktop", "dy_swidth", "dy_sheight",
    "stream_recommend_feed_params", "strategyABtestKey", "is_dash_user",
    "passport_csrf_token", "passport_csrf_token_default", "fpk1", "fpk2",
    "ttwid", "biz_trace_id", "__security_mc_1_s_sdk_crypt_sdk",
    "bd_ticket_guard_regenerate_keys_time",
)

# Explicit passport header order from the supplied browser cURL.  The
# Cookie value is serialized separately by ``headers_with_cookie``.
PASSPORT_HEADER_ORDER = (
    "accept", "accept-language", "cache-control", "content-type",
    "origin", "pragma", "priority", "referer", "sec-ch-ua",
    "sec-ch-ua-mobile", "sec-ch-ua-platform", "sec-fetch-dest",
    "sec-fetch-mode", "sec-fetch-site", "user-agent", "web-sdk-version",
    "x-tt-passport-aid-sign", "x-tt-passport-csrf-token",
    "x-tt-passport-trace-id", "x-tt-passport-verify-portrait",
    "x-tt-session-dtrait",
)

# The same reqid=4468 capture's controlled header order.  Chrome's network
# layer adds accept-encoding/content-length/cookie; these are deliberately not
# listed here because callers serialize the Cookie explicitly.
PASSPORT_HEADER_ORDER_CHROME4468 = (
    "web-sdk-version", "x-tt-session-dtrait", "referer",
    "x-tt-passport-aid-sign", "x-tt-passport-csrf-token",
    "x-tt-passport-trace-id", "user-agent", "accept", "content-type",
    "x-tt-passport-verify-portrait", "accept-encoding", "accept-language",
    "content-length", "origin", "priority",
    "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site",
)

# Fresh Chrome 151 passport XHR controlled-header order from the live SMS
# captures (reqid=608/send_code and reqid=735/sms_login).  These requests do
# **not** carry sec-ch-ua*, cache-control, or pragma.  The network layer still
# adds accept-encoding, content-length and cookie.
PASSPORT_HEADER_ORDER_CHROME_CURRENT = (
    "web-sdk-version", "x-tt-session-dtrait", "referer",
    "x-tt-passport-aid-sign", "x-tt-passport-csrf-token",
    "x-tt-passport-trace-id", "user-agent", "accept", "content-type",
    "x-tt-passport-verify-portrait", "accept-encoding", "accept-language",
    "content-length", "origin", "priority",
    "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site",
)

# QR/bootstrap passport XHRs on the same Chrome 151 page retain the browser
# client-hint trio.  The SMS form deliberately does not, so it cannot share
# PASSPORT_HEADER_ORDER_CHROME_CURRENT.  This order is taken from the live
# ``requestWillBeSentExtraInfo`` view (web-sdk-version -> platform -> dtrait
# -> referer -> ua -> passport headers), with the network-layer fields added
# after the controlled headers below.
PASSPORT_HEADER_ORDER_CHROME_CURRENT_QR = (
    "web-sdk-version", "sec-ch-ua-platform", "x-tt-session-dtrait", "referer",
    "sec-ch-ua", "x-tt-passport-aid-sign", "sec-ch-ua-mobile",
    "x-tt-passport-csrf-token", "x-tt-passport-trace-id", "user-agent",
    "accept", "content-type", "x-tt-passport-verify-portrait",
    "accept-language", "origin", "priority", "sec-fetch-dest",
    "sec-fetch-mode", "sec-fetch-site",
)


def _passport_profile(name):
    """Return an explicit browser-wire profile name.

    The live Chrome 151 capture is the default for the login flow.  The old
    pasted cURL remains available explicitly via ``legacy_curl`` so fixture
    replay does not disappear when the browser SDK rolls forward.
    """
    # The active browser baseline is Chrome 151 for both cookie and header
    # serialization.  Keep the older controlled-header fixture available via
    # an explicit ``DY_PASSPORT_HEADER_PROFILE=chrome4468`` override; it must
    # not be the implicit default because that profile is an older fixture.
    default = "chrome_current" if name in (
        "DY_PASSPORT_COOKIE_PROFILE", "DY_PASSPORT_HEADER_PROFILE") \
        else "legacy_curl"
    value = os.getenv(name, default).strip().lower()
    return value or "legacy_curl"


def _phone_login_profile():
    """Select the phone protocol without mixing its wire schemas.

    ``passport_web`` is the phone form embedded by ``www.douyin.com/jingxuan``
    (the 2026-08-29 Chrome capture).  ``sso`` is the separate bare
    ``login.douyin.com`` page and must be selected explicitly; its endpoints,
    cookie jar and query schema are different.
    """
    value = (os.getenv("DY_PHONE_LOGIN_PROFILE") or "passport_web").strip().lower()
    aliases = {"current": "passport_web", "chrome": "passport_web",
               "sms": "passport_web", "legacy": "passport_web",
               "passport": "passport_web", "login_page": "sso",
               "phone_sso": "sso"}
    return aliases.get(value, value) or "passport_web"


class _OrderedCookies(dict):
    """Ordered cookie view carrying bare-token names for wire serialization."""

    def __init__(self, *args, raw_tokens=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_tokens = set(raw_tokens or ())


def _cookie_view(auth, order):
    """Build a scoped ordered mapping without losing bare Cookie tokens."""
    jar = auth.cookie or {}
    raw = set(getattr(auth, "_raw_cookie_tokens", ()) or ())
    out = _OrderedCookies(raw_tokens=(name for name in order if name in raw))
    for name in order:
        if name in raw:
            # ``None`` is a deliberate marker: cookie_header() emits only the
            # name for entries listed in ``raw_tokens``.
            out[name] = None
        elif jar.get(name) not in (None, ""):
            out[name] = jar[name]
    return out


def scoped_cookies(auth, host="login"):
    """按域挑 Cookie 并**按实录顺序**排好。

    :param host: `login` / `sms` / `sms_login` / `phone_sso` / `www` /
        `challenge`。`sms`/`sms_login` are the passport-web phone-code jars;
        `phone_sso` is the current login-page SSO jar. `challenge` 是 login
        域的早期阶段，Cookie 集合更小，见 CHALLENGE_COOKIE_ORDER。

    ``DY_PASSPORT_COOKIE_PROFILE=chrome4468`` selects the later 25-cookie
    Chrome capture; the default remains the supplied 22-cookie cURL fixture.
    """
    if host == "challenge":
        jar = auth.cookie or {}
        profile = _passport_profile("DY_PASSPORT_COOKIE_PROFILE")
        if profile == "chrome_current":
            order = (CHROME_CURRENT_QR_REFRESH_COOKIE_ORDER
                     if getattr(auth, "_qr_refresh_ready", False)
                     else CHROME_CURRENT_CHALLENGE_COOKIE_ORDER)
        elif profile == "chrome_current_early":
            order = CHROME_EARLY_CHALLENGE_COOKIE_ORDER
        else:
            order = CHALLENGE_COOKIE_ORDER
        out = _cookie_view(auth, order)
        # A page that has already rotated a QR code may keep the opaque
        # download_guide cookie across a later challenge.  It is absent from
        # the first challenge, but Chrome appends it once present.
        if (profile == "chrome_current" and "download_guide" not in out
                and jar.get("download_guide") not in (None, "")):
            out["download_guide"] = auth.cookie["download_guide"]
        return out
    if host == "qr":
        profile = _passport_profile("DY_PASSPORT_COOKIE_PROFILE")
        if profile == "chrome4468":
            order = CHROME4468_QR_COOKIE_ORDER
        elif profile == "chrome_current":
            if getattr(auth, "_qr_refresh_ready", False):
                order = CHROME_CURRENT_QR_REFRESH_COOKIE_ORDER
            else:
                order = CHROME_CURRENT_QR_COOKIE_ORDER
        elif profile == "chrome_current_early":
            if getattr(auth, "_qr_refresh_ready", False):
                order = CHROME_EARLY_REFRESH_COOKIE_ORDER
            elif getattr(auth, "_qr_started", False):
                order = CHROME_EARLY_CHECK_COOKIE_ORDER
            else:
                order = CHROME_EARLY_QR_COOKIE_ORDER
        else:
            order = QR_COOKIE_ORDER
        return _cookie_view(auth, order)
    if host == "ticket_guard":
        return _cookie_view(auth, TICKET_GUARD_COOKIE_ORDER)
    if host in ("ttwid", "www_ttwid", "www_guiding", "www_bootstrap"):
        if host == "ttwid":
            order = TTWID_COOKIE_ORDER
        elif host == "www_ttwid":
            order = WWW_TTWID_COOKIE_ORDER
        elif host == "www_guiding":
            order = WWW_GUIDING_COOKIE_ORDER
        else:
            order = WWW_BOOTSTRAP_COOKIE_ORDER
        return _cookie_view(auth, order)
    if host == "phone_sso":
        order = PHONE_SSO_COOKIE_ORDER
    elif host == "sms":
        order = (SMS_COOKIE_ORDER
                 if _sms_cookie_profile(auth) == "historical_26"
                 else SMS_CURRENT_COOKIE_ORDER)
    elif host == "sms_login":
        if _sms_cookie_profile(auth) == "historical_26":
            order = (SMS_LOGIN_REFRESH_COOKIE_ORDER
                     if (auth.cookie or {}).get("download_guide")
                     else SMS_COOKIE_ORDER)
        else:
            # No post-submit fresh capture exists yet; preserve the same
            # 23-pair page jar as send_code until that real request is
            # captured.  Never inject historical MONITOR/UIFID/download_guide
            # values into the current lifecycle.
            order = SMS_CURRENT_COOKIE_ORDER
    else:
        order = LOGIN_COOKIE_ORDER if host == "login" else WWW_COOKIE_ORDER
    jar = auth.cookie or {}
    raw = set(getattr(auth, "_raw_cookie_tokens", ()) or ())
    out = _OrderedCookies(raw_tokens=(name for name in order if name in raw))
    for name in order:
        if name in raw:
            out[name] = None
        elif jar.get(name) not in (None, ""):
            out[name] = jar[name]
    # 表里没列到、但确实存在的，按原顺序缀在后面（别静默丢字段）
    for k, v in jar.items():
        if k in out or v in (None, ""):
            continue
        # An explicitly selected fresh 23-cookie lifecycle must not inherit
        # stale page cookies from a prior 26-cookie capture.  Without this
        # guard the fallback append below silently turns a current request
        # back into the historical 26-pair vector.
        if (host in ("sms", "sms_login")
                and _sms_cookie_profile(auth) == "current_23"
                and k in SMS_HISTORICAL_ONLY_COOKIES):
            continue
        if host in ("login", "sms", "sms_login", "phone_sso") and (
                k in WWW_ONLY_COOKIES or k in LOGIN_EXCLUDED_COOKIES):
            continue          # host-only，不跨子域
        out[k] = v
    # Raw tokens are only meaningful on www.douyin.com.  Do not leak the
    # bare domain marker into login.douyin.com passport requests.
    if host == "www":
        for token in raw:
            if token not in out:
                out[token] = None
                out.raw_tokens.add(token)
    return out


def cookie_header(cookies):
    """Serialize an ordered cookie mapping without curl_cffi re-sorting it.

    Passing ``cookies=`` to curl_cffi first converts the mapping to its cookie
    jar and then emits jar order (which is not insertion order).  The browser
    parity baseline is order-sensitive, so login requests send the serialized
    header explicitly instead.
    """
    raw = set(getattr(cookies, "raw_tokens", ()) or ())
    return "; ".join(
        name if name in raw or value is None else f"{name}={value}"
        for name, value in (cookies or {}).items()
    )


def headers_with_cookie(headers, cookies):
    """Add the serialized Cookie at Chrome's cURL position.

    Chrome's ``Copy as cURL`` output normally places ``-b`` after the request
    content type.  The live Chrome 151 passport form is more specific: the
    network layer inserts ``accept-encoding`` and ``content-length`` first,
    then emits the Cookie field, followed by ``origin``/fetch metadata.  When
    those explicit wire fields are present, insert Cookie after
    ``content-length``; otherwise retain the historical content-type position.
    curl_cffi preserves the insertion order of an explicit header mapping, so
    appending ``cookie`` at the end would produce a different header sequence
    even when the Cookie value itself is byte-for-byte correct.
    """
    out = dict(headers or {})
    if not cookies:
        return out
    value = cookie_header(cookies)
    if "content-type" not in out or "cookie" in out:
        out["cookie"] = value
        return out
    ordered = {}
    inserted = False
    for name, item in out.items():
        ordered[name] = item
        if name == "content-length":
            ordered["cookie"] = value
            inserted = True
        elif name == "content-type" and "content-length" not in out:
            ordered["cookie"] = value
            inserted = True
    if not inserted:
        ordered["cookie"] = value
    return ordered

SSO_URL = "https://sso.douyin.com"
HOME_URL = "https://www.douyin.com"
# 登录接口在 login.douyin.com 下，不是主站。
# 主站的 www.douyin.com/passport/web/get_qrcode/ 一律返回 error_code=4031
# 「网站存在安全风险」——在真实浏览器里发同样的请求也是 4031，跟客户端无关，
# 纯粹是走错了域（2026-08-16 用独立 Chrome profile 抓登出态实录确认）。
LOGIN_URL = "https://login.douyin.com"
PASSPORT_API = LOGIN_URL + "/passport/web/"

# The currently served login.douyin.com page exposes a separate, older SSO
# phone flow.  It is not a spelling variant of ``/passport/web``: the query
# schema, aid, SDK version, cookie jar and form ordering are all different.
# Keep this profile explicit so a later page rollout cannot silently mix the
# two protocols.
PHONE_SSO_SEND_API = LOGIN_URL + "/send_activation_code/v2/"
PHONE_SSO_LOGIN_API = LOGIN_URL + "/quick_login/v2/"
PHONE_SSO_SDK = {
    "passport_jssdk_version": "3.0.29",
    "passport_jssdk_type": "normal",
    "aid": "24",
    "language": "zh",
    "account_sdk_source": "sso",
}
PHONE_SSO_COOKIE_ORDER = (
    "passport_csrf_token", "passport_csrf_token_default",
    "MONITOR_WEB_ID", "biz_trace_id",
)

# 登录页 SDK 的版本标识，取自实录；版本对不上同样会被判 4031。
# 2026-08-29 用 Chrome 151 短信登录页 Network 实录重新校准；上一版停留在
# 3.4.2，服务端已经滚过版本。这批号会随抖音发版变，出问题先来核这里。
PASSPORT_SDK = {
    "passport_jssdk_version": "3.4.4",
    "passport_jssdk_type": "normal",
    "is_from_ttaccountsdk": "1",
}
# 各 SDK 子版本，实录原样带上
PASSPORT_SDK_TAIL = {
    "p_ui": "2.4.4",
    "p_ca": "4.0.26",
    "p_ca_real": "1.0.0.892",
    "account_sdk_source": "web",
    "p_js_v": "3.4.4",
    "p_js_t": "pro",
    "p_zt": "3.3.17",
    "p_ver": "1.1.3",
    "p_ver_real": "0",
    "p_bd": "1.0.1.19-fix.01",
}
# passport SDK 自己的请求签名密钥。来源：async/28872.*.js 里
#   h = (query, data, appKey) => {
#     let {str:i, arr:o} = l(query, 10), {str:s} = l(data);
#     return {sign: sha256(`${i}&${s}&app_key=${appKey}`), qs: xor5hex(o.join(","))}
#   }
# appKey 由调用方传入，用 CDP 在 sha256 调用处下断点读出明文得到。
PASSPORT_APP_KEY = "163e7ce78d58971a41f5b969996d85c2"
# 签名时这几个参数还没被加进 query（实录对账确认：它们都排在前 10 名次内
# 却不出现在 qs 里，说明是签完才追加的）
SIGN_EXCLUDE = ("sign", "qs", "msToken", "a_bogus")
# 只签按键名排序后的前 N 个 —— SDK 里是 `Object.keys(e).sort().splice(10)`。
# 注意这个窗口是**动态**的：请求少带一个字段，第 10 名就换人。
SIGN_KEY_LIMIT = 10
ENV_FILE = ".env"


class DYLoginApi:
    """登录入口。所有方法都是纯 HTTP，不启动浏览器。"""

    # 二维码实测约 60 秒失效，留点余量按 55 秒主动换
    QR_TTL = 55
    # check_qrconnect 持续限频超过这个秒数就别硬撑了，报错让用户等冷却
    THROTTLE_GIVEUP = 120
    # 轮询间隔照浏览器实测（2026-08-16，独立 profile + CDP 记 wallTime）：
    # 浏览器每个周期发 1 个 OPTIONS 预检 + 1 个 POST，POST 之间实测
    # 5.12 / 5.13 / 5.12 / 5.12 / 5.22 秒，平均 5.14。取 5.2 略慢于浏览器，
    # 保证不会比真人更激进。我们不发预检，所以请求量本来就只有浏览器一半。
    POLL_INTERVAL = 5.2
    # mssdk starts an independent page timer.  The first /web/common is a full
    # fingerprint report after the initial successful check; subsequent
    # msgType=2 behavior heartbeats are anchored to page start every 300 s.
    MS_COMMON_INTERVAL = 300.0

    def __init__(self):
        self.base_url = PASSPORT_API
        self.home_url = HOME_URL + "/"

    # ---------- 初始化 ----------
    @staticmethod
    def register_ttwid() -> str:
        """向 ttwid 注册接口换一个匿名设备标识。

        抖音首页 HTML 返回的是 acrawler 挑战页（`__ac_nonce` + `_$jsvmprt`），
        直接抓首页拿不到 ttwid，必须走这个接口。
        """
        body = {
            "region": "cn", "aid": 1768, "needFid": False,
            "service": "www.douyin.com",
            "migrate_info": {"ticket": "", "source": "node"},
            "cbUrlProtocol": "https", "union": True,
        }
        resp = requests.post("https://ttwid.bytedance.com/ttwid/union/register/",
                             headers={"content-type": "application/json",
                                      "user-agent": get_profile()["ua"]},
                             data=json.dumps(body), verify=False, timeout=20)
        return resp.cookies.get_dict().get("ttwid", "")

    @staticmethod
    def fetch_www_bootstrap(auth, *, proxies=None):
        """Load the real landing document once and absorb page Set-Cookie.

        A clean HTTP session otherwise starts without Chrome's ``__ac_nonce``;
        the real page response creates it before the first www/ttwid/check.
        Chrome's current landing flow is ``/?recommend=1`` (rather than the
        SPA ``/jingxuan`` route) and that response is also where
        ``UIFID_TEMP`` and, on some edges, ``ttwid`` are Set-Cookie'd.  The
        companion ``__ac_signature`` is produced by page acrawler JavaScript
        and is intentionally not fabricated here.
        """
        profile = get_profile()
        headers = {
            "upgrade-insecure-requests": "1",
            "user-agent": profile["ua"],
            "sec-ch-ua": profile["sec_ch_ua"],
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": profile["sec_ch_ua_platform"],
            "accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8,"
                "application/signed-exchange;v=b3;q=0.7"
            ),
            "accept-language": "zh-CN,zh;q=0.9",
            "priority": "u=0, i",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
        }
        path = os.getenv("DY_PASSPORT_BOOTSTRAP_PATH") or "/?recommend=1"
        if path.startswith("/?"):
            headers["referer"] = HOME_URL + path
        resp = auth.request(
            "GET", HOME_URL + path, headers=headers, verify=False,
            timeout=20, proxies=proxies,
        )
        merge_set_cookies(auth, resp.cookies.get_dict())
        return resp

    @staticmethod
    def _apply_ac_signature(auth, *, strict=False, url=None, referrer=None):
        """Generate ``__ac_signature`` with the page acrawler bundle in Node.

        The HTTP landing response supplies ``__ac_nonce`` but cannot execute
        the page's JavaScript.  Once the page cookie set has been assembled,
        run the verified page-shaped VMP locally and bind its output to the
        exact Cookie header used as input.  No random/empty fallback is ever
        written.
        """
        nonce = (getattr(auth, "cookie", None) or {}).get("__ac_nonce")
        if not nonce:
            if strict:
                raise RuntimeError("严格登录生成 __ac_signature 前缺少 __ac_nonce")
            return ""
        # A caller-supplied/browser-captured signature is already bound to its
        # own nonce and Cookie serialization.  Preserve it verbatim; this is
        # what makes ``DouyinAuth.open(cookie_str=...)`` a true CK handoff.
        existing = (getattr(auth, "cookie", None) or {}).get("__ac_signature")
        existing_source = (auth.cookie_source("__ac_signature")
                           if hasattr(auth, "cookie_source") else "unknown")
        if existing and existing_source in ANONYMOUS_ACCEPTED_SOURCES_BY_FIELD.get(
                "__ac_signature", ANONYMOUS_ACCEPTED_SOURCES) \
                and os.getenv("DY_REGENERATE_AC_SIGNATURE", "").lower() \
                not in {"1", "true", "yes", "on"}:
            return str(existing)
        try:
            from utils.acrawler import generate_ac_signature
            profile = get_profile()
            result = generate_ac_signature(
                nonce,
                getattr(auth, "cookie_str", None)
                or "; ".join(f"{k}={v}" for k, v in auth.cookie.items()),
                url=url or (HOME_URL + "/jingxuan"),
                referrer=referrer or (HOME_URL + "/jingxuan"),
                ua=profile.get("ua"),
                strict=bool(strict),
            )
        except Exception as err:
            if strict:
                raise RuntimeError("严格登录无法执行 page acrawler 生成 __ac_signature") from err
            logger.warning(f"执行 page acrawler 失败，暂不写入 __ac_signature: {err}")
            return ""
        sig = str(result.get("sig") or "")
        if not sig:
            if strict:
                raise RuntimeError("严格登录 page acrawler 未产出 __ac_signature")
            return ""
        auth.cookie["__ac_signature"] = sig
        marker = getattr(auth, "mark_cookie_source", None)
        if marker:
            marker("__ac_signature", "node_page_js",
                   detail=f"acrawler VMP variant={result.get('variant', '')}")
        for name, value in (result.get("cookie_mutations") or {}).items():
            if name == "__ac_signature":
                continue
            auth.cookie[name] = value
            if marker:
                marker(name, "node_page_js", detail="acrawler cookie mutation")
        auth.cookie_str = "; ".join(f"{k}={v}" for k, v in auth.cookie.items())
        return sig

    @staticmethod
    def check_ttwid_www(auth) -> bool:
        """Run the page-origin ``POST www.douyin.com/ttwid/check/`` hop."""
        profile = get_profile()
        headers = {
            "referer": HOME_URL + "/jingxuan",
            "user-agent": profile["ua"],
            "accept": "application/json, text/plain, */*",
            "x-secsdk-csrf-token": "DOWNGRADE",
            "content-type": "application/json",
            "accept-language": "zh-CN,zh;q=0.9",
            "origin": HOME_URL,
            "priority": "u=1, i",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        body = json.dumps({"aid": 6383, "service": "www.douyin.com"},
                          separators=(",", ":"))
        resp = auth.request(
            "POST", HOME_URL + "/ttwid/check/",
            headers=headers_with_cookie(
                headers, scoped_cookies(auth, "www_ttwid")
            ),
            data=body, verify=False, timeout=20,
        )
        got = resp.cookies.get_dict()
        merge_set_cookies(auth, got)
        if got.get("ttwid"):
            auth._ttwid = got["ttwid"]
            return True
        return False

    @staticmethod
    def login_guiding_strategy(auth) -> dict:
        """Mirror the current www login-guidance GET before ``get_sec_ts``."""
        path = "/passport/general/login_guiding_strategy/"
        params = DYLoginApi._sdk_params(
            auth, data=None, device_fp=False,
            with_p_ui=False, with_request_host=True,
        )
        params.with_a_bogus(host="www.douyin.com")
        profile = get_profile()
        trace = auth.cookie.get("biz_trace_id") or ""
        headers = {
            # This is an actual empty field in the first page request.
            "x-tt-passport-csrf-token": (
                auth.cookie.get("passport_csrf_token")
                or auth.cookie.get("passport_csrf_token_default") or ""
            ),
            "referer": HOME_URL + "/jingxuan",
            "user-agent": profile["ua"],
            "accept": "application/json, text/javascript",
            "x-tt-passport-aid-sign": DYLoginApi._aid_sign(
                path, DYLoginApi._sdk_ts()
            ),
            "x-tt-passport-trace-id": trace,
            "accept-language": "zh-CN,zh;q=0.9",
            "origin": HOME_URL,
            "priority": "u=1, i",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        # The captured request has no body and sends the cookie after the
        # network-layer fetch fields, so do not pass a content type here.
        resp = auth.request(
            "GET", HOME_URL + path,
            headers=headers_with_cookie(
                headers, scoped_cookies(auth, "www_guiding")
            ),
            params=params.get(), verify=False, timeout=20,
        )
        set_cookies = resp.cookies.get_dict()
        merge_set_cookies(auth, set_cookies)
        try:
            res = resp.json()
        except Exception:
            return {"raw": resp.text[:200], "status": resp.status_code}
        DYLoginApi._raise_if_blocked("login_guiding_strategy/", res)
        return res

    @staticmethod
    def check_ttwid(auth) -> bool:
        """`POST login.douyin.com/ttwid/check/` —— 让 ttwid 在**登录域**上过一道。

        2026-08-22 实录（reqid=310）里，浏览器加载登录页后就打这个，
        而且响应会 **Set-Cookie 重新签发 ttwid**（值的后半段变了）：

            请求 ttwid: 1|n-nv123...|1787384253|3b8f4048f716007c...
            响应 ttwid: 1|n-nv123...|1787384255|01d2f9131bff94c9...

        也就是说 `ttwid.bytedance.com/ttwid/union/register/` 换来的那个只是
        「注册过」，还要在 login 域 check 一次才算「这个域认它」。
        我们以前整个跳过了这一步，带着未 check 的 ttwid 去取二维码。

        body 极简：`{"aid":6383,"service":"www.douyin.com"}`。
        """
        profile = get_profile()
        headers = {
            "referer": HOME_URL + "/",
            "user-agent": profile["ua"],
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "accept-language": "zh-CN,zh;q=0.9",
            "origin": HOME_URL,
            "priority": "u=1, i",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        }
        body = json.dumps({"aid": 6383, "service": "www.douyin.com"},
                          separators=(",", ":"))
        resp = auth.request("POST", LOGIN_URL + "/ttwid/check/",
                             headers=headers_with_cookie(headers, scoped_cookies(auth, "ttwid")),
                             data=body,
                             verify=False, timeout=20)
        got = resp.cookies.get_dict()
        merge_set_cookies(auth, got)
        if got.get("ttwid"):
            auth._ttwid = got["ttwid"]
            return True
        return False

    # ---------- 当前登录页的手机号 SSO 流 ----------
    @staticmethod
    def _phone_sso_source_info(auth=None) -> str:
        """Build the exact ``account_sdk_source_info`` shape used by aid=24.

        This is deliberately separate from ``_sdk_source_info``.  The live
        phone page sends a compact 3.0.29 SSO probe whose keys include the
        misspelled ``stoargeStatus`` and omit the web passport ``browser.t`` /
        ``automation`` envelope.  Reusing the newer web probe changes both
        ciphertext and length.
        """
        p = get_profile()
        g = p["geo"]

        def env_number(name, default):
            value = os.getenv(name)
            if value in (None, ""):
                return default
            try:
                return float(value) if any(ch in value for ch in ".eE") else int(value)
            except (TypeError, ValueError):
                return default

        info = {
            "hardwareConcurrency": int(p["cpu_core_num"]),
            "webdriver": False,
            "chromedriver": False,
            "shelldriver": False,
            "plugins": 5,
            "permissions": [{"name": "notifications", "state": "prompt"}],
            "innerHeight": g[1],
            "innerWidth": g[0],
            "outerHeight": g[3],
            "outerWidth": g[2],
            "stoargeStatus": {
                "indexedDB": {
                    "idb": "object", "open": "function",
                    "indexedDB": "object", "IDBKeyRange": "function",
                    "openDatabase": "undefined", "isSafari": False,
                    "hasFetch": False,
                },
                "localStorage": {
                    "isSupportLStorage": True,
                    "size": env_number("DY_PHONE_SSO_STORAGE_SIZE", 590),
                    "write": True,
                },
                "storageQuotaStatus": {
                    "usage": 0, "quota": 6442450944, "isPrivate": False,
                },
            },
            "webgl": {
                "vendor": p["webgl_vendor"],
                "renderer": p["webgl_renderer"],
            },
            "notificationPermission": "default",
            "performance": {
                "timeOrigin": env_number(
                    "DY_PHONE_SSO_TIME_ORIGIN_MS",
                    getattr(auth, "_phone_page_started_ms", None)
                    or round(time.time() * 1000, 1)),
                "usedJSHeapSize": env_number(
                    "DY_PHONE_SSO_USED_JS_HEAP_SIZE", 15073598),
                "navigationTiming": {
                    "decodedBodySize": env_number(
                        "DY_PHONE_SSO_DECODED_BODY_SIZE", 3745),
                    "entryType": "navigation",
                    "initiatorType": "navigation",
                    "name": os.getenv("DY_PHONE_SSO_PAGE_URL")
                    or LOGIN_URL + "/",
                    "renderBlockingStatus": "non-blocking",
                    "serverTiming": os.getenv(
                        "DY_PHONE_SSO_SERVER_TIMING", "inner,cdn-cache,edge,origin"),
                    "guleStart": "none",
                    "guleDuration": "none",
                },
            },
            "request_host": "login.douyin.com",
            "request_pathname": "/",
            "browser": {},
        }
        return passport_encrypt(json.dumps(
            info, ensure_ascii=False, separators=(",", ":")))

    @staticmethod
    def _phone_sso_params(auth) -> Params:
        """Return the seven-key SSO query in Chrome's insertion order."""
        if not auth.cookie.get("biz_trace_id"):
            auth.cookie["biz_trace_id"] = (
                os.getenv("DY_PASSPORT_FIXED_BIZ_TRACE_ID")
                or secrets.token_hex(4)
            )
        params = Params()
        for key, value in PHONE_SSO_SDK.items():
            params.add_param(key, value)
        params.add_param("account_sdk_source_info", DYLoginApi._phone_sso_source_info(auth))
        params.add_param("biz_trace_id", auth.cookie["biz_trace_id"])
        return params

    @staticmethod
    def _phone_sso_headers(auth, cookies=None):
        """Build current page SSO headers; no passport-web-only headers."""
        profile = get_profile()
        csrf = (auth.cookie.get("passport_csrf_token")
                or auth.cookie.get("passport_csrf_token_default") or "")
        trace = auth.cookie.get("biz_trace_id") or ""
        # The first six entries are the controlled XHR headers seen in the
        # page hook.  The remaining entries are browser network-layer fields
        # that curl_cffi does not synthesize when default_headers=False.
        headers = {
            "accept": "application/json, text/javascript",
            "content-type": "application/x-www-form-urlencoded",
            "x-tt-passport-csrf-token": csrf,
            "x-tt-passport-trace-id": trace,
            "referer": LOGIN_URL + "/",
            "user-agent": profile["ua"],
            "accept-language": "zh-CN,zh;q=0.9",
            "origin": LOGIN_URL,
            "priority": "u=1, i",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        return headers_with_cookie(
            headers, cookies if cookies is not None else scoped_cookies(auth, "phone_sso"))

    @staticmethod
    def bootstrap_phone_auth(proxies=None) -> DouyinAuth:
        """Bootstrap the current login-page phone session without QR traffic.

        A browser opened directly on the phone tab starts with only the two
        CSRF cookies from the document response.  ``MONITOR_WEB_ID`` is then
        written by the page SDK and ``biz_trace_id`` is created on the first
        button click.  Calling the QR/bootstrap chain here would introduce a
        different Cookie set and a different protocol.
        """
        auth = DouyinAuth()
        # Keep the same CookieDict/owner bridge as the main bootstrap.  The
        # SSO page starts empty, but its document response immediately fills
        # CSRF cookies and all later requests must stay on this Auth Session.
        auth.cookie = bind_cookie_owner(CookieDict(), auth)
        auth.cookie_str = ""
        auth.phone_login_profile = "sso"
        auth._proxies = proxies
        auth._phone_page_started_ms = round(time.time() * 1000, 1)
        try:
            resp = auth.request(
                "GET", LOGIN_URL + "/",
                headers={
                    "upgrade-insecure-requests": "1",
                    "user-agent": get_profile()["ua"],
                    "accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/avif,image/webp,image/apng,*/*;q=0.8,"
                        "application/signed-exchange;v=b3;q=0.7"
                    ),
                    "accept-language": "zh-CN,zh;q=0.9",
                    "priority": "u=0, i",
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "none",
                    "sec-fetch-user": "?1",
                },
                verify=False, timeout=20, proxies=proxies,
            )
            merge_set_cookies(auth, resp.cookies.get_dict())
        except Exception as err:
            raise RuntimeError("手机号登录页初始化失败，未拿到 CSRF Cookie") from err
        if not auth.cookie.get("passport_csrf_token"):
            raise RuntimeError("手机号登录页响应缺少 passport_csrf_token，已拒绝继续")
        # Slardar writes this client-side UUID before the first SSO XHR.
        auth.cookie.setdefault(
            "MONITOR_WEB_ID",
            os.getenv("DY_PHONE_SSO_MONITOR_WEB_ID") or str(uuid.uuid4()),
        )
        auth.private_key, _ = generate_ec_keypair()
        auth.cookie_str = "; ".join(
            f"{k}={v}" for k, v in auth.cookie.items())
        return auth

    @staticmethod
    def bootstrap_auth(cookie_str: str = "", *, strict: bool = False,
                       proxies=None) -> DouyinAuth:
        """准备一个可用于登录的 auth：自生成密钥 + 拉取匿名 Cookie。

        `s_v_web_id` 本地生成，`ttwid` 走注册接口，`passport_csrf_token` 由
        passport 接口的 Set-Cookie 下发。`strict=True` 仅用于短信登录：
        challenge/template、dtrait、ttwid、sec_ts 和 ticket-guard 任一步
        缺失就停止，不带着伪造字段继续请求。
        """
        auth = DouyinAuth()
        auth.strict_browser_alignment = bool(strict)
        auth._proxies = proxies
        # If this auth is later reused for the historical SMS helper, keep it
        # on the passport-web schema; the direct phone bootstrap sets ``sso``
        # explicitly below.
        auth.phone_login_profile = "passport_web"
        auth.perepare_auth(cookie_str, "", "")
        # .env 必须**在任何 os.getenv 之前**载入。登录脚本不像 `init()` 那样先跑
        # `load_env()`，之前把 load_dotenv 放在函数末尾，导致中间所有
        # `os.getenv` 全取空值 —— 这个坑让扫码登录长期缺 x-tt-session-dtrait，
        # 表现是 check_qrconnect 返回 `error_code=7 访问太频繁`（服务端兜底话术），
        # 看着像限频。现在设备类 Cookie（DY_ODIN_TT 等）也依赖它，顺序更不能错。
        try:
            from dotenv import load_dotenv
            load_dotenv(ENV_FILE)
        except Exception as err:
            logger.warning(f"载入 {ENV_FILE} 失败，设备素材可能缺失: {err}")
        # 登录用的 EC 密钥对由我们自己生成，登录响应会据此签发 ticket
        auth.private_key, _pub = generate_ec_keypair()
        # 公钥必须在**取二维码之前**就通过 Cookie 交给服务端：zero.js 把它写进
        # bd_ticket_guard_client_data，登录接口据此把 ticket 签给这把公钥。
        # 缺了这个 Cookie，扫码能成功、Cookie 能落，但响应里永远没有
        # bd-ticket-guard-server-data，于是拿不到 ticket/ts_sign——
        # 后续 create_v2、发评论这类强校验接口就全都做不了。
        auth.cookie[CLIENT_DATA_COOKIE] = build_client_data_cookie(auth.private_key)
        auth.cookie[CLIENT_WEB_DOMAIN_COOKIE] = "2"

        # A clean HTTP lifecycle first loads the actual jingxuan document. It
        # is the source for the short-lived __ac_nonce Set-Cookie; the page's
        # JS may subsequently add __ac_signature, so preserve any captured
        # value and never invent one here.
        try:
            DYLoginApi.fetch_www_bootstrap(auth)
        except Exception as err:
            logger.warning(f"加载 jingxuan 页面 bootstrap 失败: {err}")
            if strict and not auth.cookie.get("__ac_nonce"):
                raise RuntimeError(
                    "严格短信登录要求 jingxuan 页面下发 __ac_nonce"
                ) from err

        if not auth.cookie.get("ttwid"):
            try:
                ttwid = DYLoginApi.register_ttwid()
                if ttwid:
                    auth.cookie["ttwid"] = ttwid
            except Exception as err:
                logger.warning(f"注册 ttwid 失败: {err}")
                if strict:
                    raise RuntimeError("严格短信登录要求注册 ttwid 成功") from err
            if strict and not auth.cookie.get("ttwid"):
                raise RuntimeError(
                    "严格短信登录要求存在 ttwid；注册接口未返回有效 Cookie"
                )

        auth.cookie.pop("msToken", None)
        auth.cookie.setdefault("s_v_web_id", generate_s_v_web_id())
        # biz_trace_id 浏览器是 query / 请求头 / Cookie 三处同一个值。以前只在
        # `_sdk_params` 里临时随机一个塞进 query，Cookie 里没有，于是
        # `_passport_headers` 取不到值、`x-tt-passport-trace-id` 整个头被跳过。
        auth.cookie.setdefault(
            "biz_trace_id",
            os.getenv("DY_PASSPORT_FIXED_BIZ_TRACE_ID") or secrets.token_hex(4),
        )
        DYLoginApi._add_page_cookies(auth)
        # Keep the serialized input in lockstep with the just-added page
        # cookies.  acrawler signs the document.cookie snapshot; using the
        # pre-page ``cookie_str`` here would produce a valid-looking but
        # wrong signature for the real request.
        auth.cookie_str = "; ".join(f"{k}={v}" for k, v in auth.cookie.items())
        # The landing response only gives us __ac_nonce.  Execute the page
        # acrawler bundle locally after the complete page-cookie shape is
        # assembled so www/ttwid/check and the first passport call can carry a
        # real signature even when no browser is running.
        try:
            DYLoginApi._apply_ac_signature(
                auth, strict=bool(strict),
                url=HOME_URL + "/jingxuan",
                referrer=HOME_URL + "/jingxuan",
            )
        except Exception as err:
            logger.warning(f"生成 __ac_signature 失败: {err}")
            if strict:
                raise
        # Do not confuse a shape-correct random fallback with browser
        # evidence.  In strict mode every opaque anonymous field must have
        # come from caller capture, an actual Set-Cookie, or an explicit
        # browser-runtime handoff before the first passport request.
        if strict:
            # bit_env can be derived only after the challenge returns
            # passportiv.  Defer that one field's strict proof until then;
            # the other opaque values are required for the first passport
            # request itself.
            _assert_anonymous_cookie_evidence(
                auth, context="passport",
                required_names=("UIFID_TEMP", "odin_tt",
                                "passport_auth_mix_state"),
            )
        auth.cookie_str = "; ".join(f"{k}={v}" for k, v in auth.cookie.items())
        # ⚠️ 这两样必须在**任何网络请求之前**准备好。
        # 它们原来排在 challenge/get_qrcode 之后，导致首个 passport 请求
        # （challenge）缺 x-tt-passport-verify-portrait 和 x-tt-session-dtrait
        # 两个头 —— 而实录里浏览器**从第一发起就带着**。
        #
        # `x-tt-passport-verify-portrait`：形如 `<uuid>.login`，一次登录会话一个。
        # 早先判断「正常流程浏览器不发这个头」是错的 —— 实录里
        # challenge / get_qrcode / check_qrconnect 三个请求都带着它。
        auth.verify_portrait = (
            os.getenv("DY_PASSPORT_FIXED_VERIFY_PORTRAIT")
            or f"{uuid.uuid4()}.login"
        )
        # dtrait blob 是**设备**绑定而不是会话绑定：重新登录、换账号都照样有效。
        # 优先沿用显式素材；没有显式素材时，DouyinAuth 已加载由 DevTools
        # 取证固化的设备档案，并在每个请求按当前 path 纯算内层 blob。
        # （.env 已在函数开头载入。）
        auth.dtrait_blob = os.getenv("DY_DTRAIT_BLOB") or None
        auth.session_dtrait = os.getenv("DY_SESSION_DTRAIT") or None
        if not auth.dtrait_blob and not auth.dtrait_profile and not auth.session_dtrait:
            logger.warning("没有 dtrait 素材（DY_DTRAIT_BLOB / DY_DTRAIT_PROFILE / "
                           "DY_SESSION_DTRAIT 都为空），passport 请求会缺 "
                           "x-tt-session-dtrait，可能被判需二次验证")
            if strict:
                raise RuntimeError(
                    "严格短信登录缺少 DY_DTRAIT_BLOB / DY_DTRAIT_PROFILE / "
                    "DY_SESSION_DTRAIT；"
                    "不能用猜测值代替 x-tt-session-dtrait"
                )
        # Current Chrome 151 ordering on jingxuan is:
        #   www/ttwid/check -> login_guiding_strategy -> get_sec_ts
        # The guiding response writes passport_csrf_token(_default), so these
        # hops must happen before get_sec_ts and the first request must not
        # carry a pre-seeded CSRF pair.
        if strict:
            missing = [
                name for name in ("__ac_nonce", "__ac_signature")
                if not auth.cookie.get(name)
            ]
            unproven = [
                name for name in ("__ac_nonce", "__ac_signature")
                if auth.cookie.get(name)
                and auth.cookie_source(name) not in ANONYMOUS_ACCEPTED_SOURCES_BY_FIELD.get(
                    name, ANONYMOUS_ACCEPTED_SOURCES)
            ]
            if missing or unproven:
                raise RuntimeError(
                    "严格短信登录缺少 www 页面 acrawler Cookie: "
                    + ", ".join(missing)
                    + ("；来源未证明: " + ", ".join(unproven)
                       if unproven else "")
                    + "；不能用空值或随机值代替"
                )
        try:
            if not DYLoginApi.check_ttwid_www(auth):
                logger.warning("www/ttwid/check 没换回新 ttwid")
                if strict:
                    raise RuntimeError("严格短信登录要求 www/ttwid/check 成功")
        except Exception as err:
            logger.warning(f"www/ttwid/check 失败: {err}")
            if strict:
                raise RuntimeError("严格短信登录要求 www/ttwid/check 成功") from err
        try:
            guiding = DYLoginApi.login_guiding_strategy(auth)
            if (guiding or {}).get("message") != "success":
                logger.warning(
                    f"login_guiding_strategy 未成功: {str(guiding)[:200]}"
                )
                if strict:
                    raise RuntimeError(
                        "严格短信登录要求 login_guiding_strategy 返回 success"
                    )
        except Exception as err:
            logger.warning(f"login_guiding_strategy 失败: {err}")
            if strict:
                raise RuntimeError(
                    "严格短信登录要求 login_guiding_strategy 成功"
                ) from err

        # 浏览器加载登录页时的第一跳就是 get_sec_ts，它的响应头给出 sec_ts，
        # SDK 据此写 bd_ticket_guard_client_data_v2 Cookie。照抄这个时序，
        # 后面每个 passport 请求就都带得上这个 Cookie。
        try:
            DYLoginApi.get_sec_ts(auth)
        except Exception as err:
            logger.warning(f"get_sec_ts 失败，client_data_v2 会缺: {err}")
            if strict:
                raise RuntimeError("严格短信登录要求 get_sec_ts 成功") from err
        # 紧接着是 ttwid/check —— 让 ttwid 在登录域上过一道并换发新值。
        # 时序照实录：get_sec_ts -> ttwid/check -> challenge -> get_qrcode
        try:
            if not DYLoginApi.check_ttwid(auth):
                logger.warning("ttwid/check 没换回新 ttwid，登录域可能不认这个设备标识")
                if strict:
                    raise RuntimeError("严格短信登录要求 ttwid/check 成功")
        except Exception as err:
            logger.warning(f"ttwid/check 失败: {err}")
            if strict:
                raise RuntimeError("严格短信登录要求 ttwid/check 成功") from err
        # Bind the mssdk token request to the ttwid just accepted by the login
        # domain.  Leaving _ttwid empty here makes get_mstoken fall back to a
        # stale DY_COOKIES value and produces a different token length/value.
        auth._ttwid = auth.cookie.get("ttwid", "")
        # Any stale v2 from an input jar belongs to a previous ticket cycle;
        # Chrome omits it until a later page-side refresh.
        auth.cookie.pop(CLIENT_DATA_V2_COOKIE, None)
        auth.cookie_str = "; ".join(f"{k}={v}" for k, v in auth.cookie.items())
        # challenge：设备认证。响应会下发 passport_csrf_token，
        # 所以必须排在 get_qrcode 之前（浏览器就是这个顺序）。
        try:
            res = DYLoginApi.challenge(auth, strict=strict)
            if (res or {}).get("message") != "success":
                logger.warning(f"challenge 未成功: {str(res)[:200]}")
                if strict:
                    raise RuntimeError(
                        "严格短信登录要求 challenge 返回 success；"
                        f"实际响应: {str(res)[:300]}"
                    )
        except Exception as err:
            logger.warning(f"challenge 失败: {err}")
            if strict:
                raise RuntimeError("严格短信登录要求 challenge 成功") from err
        if strict:
            # ``passportiv`` is available only in the challenge response and
            # is the input to the local AES-CBC bit_env derivation.  Verify it
            # now, after _apply_challenge_template has had a chance to write
            # the derived value.
            _assert_anonymous_cookie_evidence(
                auth, context="passport challenge", required_names=("bit_env",)
            )
        # Chrome performs ticket_guard/get_client_cert immediately after the
        # challenge and before get_qrcode.  The page SDK consumes its result
        # to create bd_ticket_guard_client_data_v2; omitting this step leaves
        # the QR/check requests one Cookie short and changes the encrypted
        # client-data binding.  Keep v2 out of the challenge jar
        # (CHALLENGE_COOKIE_ORDER deliberately excludes it), but make it
        # available to the subsequent QR jar.
        # Chrome has two observed SDK lifecycles.  The fresh isolated profile
        # (``chrome_current_early``) sends get_qrcode before the ticket-guard
        # client-cert request; defer v2 generation until get_qrcode returns.
        # The older/current profile keeps the already verified
        # challenge -> client-cert -> get_qrcode ordering.
        early_profile = _passport_profile("DY_PASSPORT_COOKIE_PROFILE") \
            == "chrome_current_early"
        if early_profile:
            auth._defer_client_data_v2 = True
        else:
            try:
                if not DYLoginApi._add_client_data_v2(auth):
                    logger.warning("challenge 后未能生成 bd_ticket_guard_client_data_v2")
                    if strict:
                        raise RuntimeError(
                            "严格短信登录要求 challenge 后生成 bd_ticket_guard_client_data_v2"
                        )
            except Exception as err:
                logger.warning(f"challenge 后初始化 client_data_v2 失败: {err}")
                if strict:
                    raise RuntimeError(
                        "严格短信登录要求 challenge 后初始化 client_data_v2 成功"
                    ) from err
        auth._ttwid = auth.cookie.get("ttwid", "")
        return auth

    # ---------- 公共参数 / 请求头 ----------
    @staticmethod
    def _add_page_cookies(auth):
        """补齐**页面 JS 自己写的**那批 Cookie。

        常量、设备测量值和可逆编码字段可以在本地重建；
        `UIFID_TEMP` / `odin_tt` / `bit_env` / `passport_auth_mix_state`
        则属于不透明会话材料。当前证据只支持“从真实页面/响应/浏览器运行时
        捕获后复用”，不支持从零确定性生成。长度正确的随机值仅在显式设置
        ``DY_ALLOW_SYNTHETIC_ANONYMOUS_COOKIES=1`` 时作为宽松兼容选项，并会被
        标记为 ``unproven_synthetic``；默认不生成，严格模式始终拒绝。
        """
        p = get_profile()
        c = auth.cookie
        cookie_profile = _passport_profile("DY_PASSPORT_COOKIE_PROFILE")
        sms_profile = _sms_cookie_profile(auth)
        current_chrome = cookie_profile == "chrome_current"
        modern_chrome = cookie_profile in ("chrome_current", "chrome_current_early")
        # —— 纯常量，实录原样 ——
        c.setdefault("enter_pc_once", "1")
        c.setdefault("is_support_rtm_web_ts", "1")
        c.setdefault("hevc_supported", "true")
        c.setdefault("IsDouyinActive", "true")
        # Current Chrome 151 writes this media-capability marker before the
        # first passport challenge.  It is absent from the legacy pasted cURL,
        # so keep it scoped to the explicit current profile.
        if current_chrome:
            c.setdefault("is_dash_user", "1")
        c.setdefault("my_rd", "2")
        # 值是 JSON 串 "0" 再整体 URL 编码
        c.setdefault("home_can_add_dy_2_desktop",
                     "%221%22" if cookie_profile == "chrome_current_early"
                     else "%220%22")
        # 3.4.2 页面启动时写入的 AB 实验标记会跨域带到 login 域。
        # 实录格式为 URL 编码后的 JSON 字符串：%22<epoch-seconds.millis>%22。
        # Chrome writes the value as a JSON string containing epoch seconds
        # with exactly three fractional digits.  Keep this value on the same
        # fixed-clock used by the other passport fields when parity debugging
        # is enabled; otherwise a second-by-second drift changes both the
        # Cookie bytes and the passport sign window.
        fixed_strategy = os.getenv("DY_PASSPORT_FIXED_STRATEGY_ABTEST_KEY")
        if not fixed_strategy:
            fixed_ms = (os.getenv("DY_PASSPORT_FIXED_SOURCE_TIME_MS")
                        or os.getenv("DY_FIXED_TIMESTAMP_MS"))
            if fixed_ms:
                try:
                    fixed_strategy = f"{float(fixed_ms) / 1000:.3f}"
                except ValueError:
                    fixed_strategy = None
        if not fixed_strategy:
            fixed_strategy = f"{time.time():.3f}"
        # Accept either the raw numeric value or the already JSON/URL encoded
        # form when a capture is supplied explicitly.
        if fixed_strategy.startswith("%22"):
            strategy_cookie = fixed_strategy
        else:
            strategy_cookie = urllib.parse.quote(json.dumps(str(fixed_strategy)))
        c.setdefault("strategyABtestKey", strategy_cookie)
        # —— 这三个只在 www.douyin.com 域（host-only），不跨到 login 子域 ——
        c.setdefault("dy_swidth", str(int(p["screen_width"])))
        c.setdefault("dy_sheight", str(int(p["screen_height"])))
        # The www ticket-guard request contains the same high-entropy
        # navigator values exposed by Chrome's page SDK.
        c.setdefault("device_web_cpu_core", str(int(p["cpu_core_num"])))
        c.setdefault("device_web_memory_size", str(int(p["device_memory"])))
        c.setdefault("architecture", os.getenv("DY_FP_ARCHITECTURE", "amd64"))
        # 安全 SDK 的运行时 uid，实录是 uuid v4（localStorage 里也存了一份
        # web_runtime_security_uid，同值）
        c.setdefault("x-web-secsdk-uid", str(uuid.uuid4()))
        # —— 设备指纹，必须与 query 的 screen_* / cpu_core_num / device_memory 同源 ——
        # goal.md「指纹必须与 cookie 自洽」记的就是这个 Cookie：
        # 它写死了屏幕尺寸 / 核数 / 内存，和 query 对不上一比就露。
        feed_params = {
            "cookie_enabled": True,
            "screen_width": int(p["screen_width"]),
            "screen_height": int(p["screen_height"]),
            "browser_online": True,
            "cpu_core_num": int(p["cpu_core_num"]),
            "device_memory": int(p["device_memory"]),
            "downlink": 10,
            "effective_type": "4g",
            # The live 2026-08-23 page reports 0 here.  The legacy capture
            # reports 50; allow an explicit override for fixture replay.
            "round_trip_time": int(os.getenv(
                "DY_FP_ROUND_TRIP_TIME",
                "0" if modern_chrome else "50")),
        }
        c.setdefault("stream_recommend_feed_params", urllib.parse.quote(
            json.dumps(json.dumps(feed_params, separators=(",", ":")),
                       ensure_ascii=False), safe=""))
        # —— 安全 SDK 的实例 id：实录形如 c41da905-45e7-9bb4（8-4-4 hex）——
        c.setdefault("__security_mc_1_s_sdk_crypt_sdk",
                     "%s-%s-%s" % (secrets.token_hex(4), secrets.token_hex(2),
                                   secrets.token_hex(2)))
        # —— 密钥轮换时刻，本地时间 YYYY-MM-DD/HH:MM:SS ——
        c.setdefault("bd_ticket_guard_regenerate_keys_time",
                     time.strftime("%Y-%m-%d/%H:%M:%S"))
        # Opaque anonymous values are not locally reproducible.  A value may
        # be supplied by the caller, observed in a real Set-Cookie response,
        # or imported from an explicitly selected browser capture.  Never
        # imply that a random string is an implementation of the page rule.
        # Explicit environment overrides are user-supplied capture material,
        # not synthetic fallbacks. Absorb them before strict provenance
        # checks so a browser capture can be resumed without another flag.
        # DY_USE_CAPTURED_BOOTSTRAP_COOKIES remains accepted for compatibility
        # but no longer gates explicitly supplied values.
        for env_key, name in (("DY_UIFID_TEMP", "UIFID_TEMP"),
                              ("DY_ODIN_TT", "odin_tt"),
                              ("DY_BIT_ENV", "bit_env"),
                              ("DY_PASSPORT_AUTH_MIX_STATE",
                               "passport_auth_mix_state"),
                              ("DY_AC_NONCE", "__ac_nonce"),
                              ("DY_AC_SIGNATURE", "__ac_signature"),
                              ("DY_FPK1", "fpk1"),
                              ("DY_FPK2", "fpk2")):
            v = os.getenv(env_key)
            if v:
                if name not in c:
                    c[name] = v
                marker = getattr(auth, "mark_cookie_source", None)
                if marker and c.get(name) == v:
                    marker(name, "captured_input", detail=f"env:{env_key}")

        # fpk2 is a true pure rule: lowercase MD5 of the full User-Agent.
        # fpk1's *algorithm* is known, but its inputs are device-bound
        # FingerprintJS values (canvas/fonts/WebGL/audio/plugins).  The
        # project ships one captured component fixture so a clean, browserless
        # install can still attempt phone login.  It is a compatibility
        # fallback, not proof of the caller's physical device; callers with a
        # browser capture should continue to provide DY_FPK1 (or a matching
        # DY_FP_COMPONENTS_FILE).  Set DY_AUTO_LOCAL_FPK1=0 to restore the
        # previous fail-closed behavior.
        marker = getattr(auth, "mark_cookie_source", None)
        if not c.get("fpk2"):
            c["fpk2"] = build_fpk2(p["ua"])
            if marker:
                marker("fpk2", "local_pure", detail="md5(full user-agent)")
        if not c.get("fpk1"):
            allow_local_fpk1 = os.getenv("DY_ALLOW_LOCAL_FPK1", "").lower() \
                in {"1", "true", "yes", "on"}
            auto_local_fpk1 = os.getenv("DY_AUTO_LOCAL_FPK1", "1").lower() \
                not in {"0", "false", "no", "off"}
            fixture_path = os.getenv("DY_FP_COMPONENTS_FILE")
            if not fixture_path:
                fixture_path = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..", "utils",
                                 "challenge_profile.json")
                )
            if (fixture_path and (allow_local_fpk1 or auto_local_fpk1)
                    and os.path.isfile(fixture_path)):
                try:
                    c["fpk1"] = build_fpk1()
                except Exception as error:
                    logger.warning(f"本地 fpk1 纯算失败，将继续走严格校验: {error}")
                else:
                    if marker:
                        marker("fpk1", "local_pure_fixture",
                               detail=f"fingerprintjs fixture:{fixture_path}")
                    logger.warning(
                        "未捕获当前浏览器 fpk1，已使用项目内 FingerprintJS fixture "
                        "纯算；如遇风控，请提供同一设备的 DY_FPK1 或组件文件"
                    )
            if (not c.get("fpk1")
                    and getattr(auth, "strict_browser_alignment", False)):
                raise RuntimeError(
                    "严格登录无法生成 fpk1；请在 CK 中提供 fpk1，或提供有效的 "
                    "DY_FP_COMPONENTS_FILE（可设置 DY_AUTO_LOCAL_FPK1=1 使用项目默认 fixture）"
                )

        # The mix-state rule is fully recovered: sample a fresh state locally
        # when no captured/server value was supplied. This is valid pure
        # generation (the value is intentionally random per page session),
        # unlike UIFID_TEMP/odin_tt which remain server/browser material.
        if "passport_auth_mix_state" not in c:
            mix_len = 48 if modern_chrome and sms_profile != "historical_26" else 32
            c["passport_auth_mix_state"] = generate_passport_auth_mix_state(mix_len)
            if marker:
                marker("passport_auth_mix_state", "local_pure_random",
                       detail="recovered Math.random length/alphabet rule")

        # Compatibility fallback for old relaxed callers. Synthetic values
        # are opt-in only: absence of a capture must never silently create a
        # random Cookie that looks like a browser value. Strict mode always
        # rejects these values, even when the opt-in flag is present.
        allow_synthetic = os.getenv(
            "DY_ALLOW_SYNTHETIC_ANONYMOUS_COOKIES", ""
        ).lower() in {"1", "true", "yes", "on"}
        if (allow_synthetic
                and not getattr(auth, "strict_browser_alignment", False)):
            synthetic = {
                "UIFID_TEMP": secrets.token_hex(112 if modern_chrome else 80),
                "odin_tt": secrets.token_hex(80),
                "bit_env": secrets.token_urlsafe(384)[:512],
                # mix-state is already generated above by its proven rule;
                # keep this map limited to opaque compatibility placeholders.
            }
            for name, value in synthetic.items():
                if name not in c:
                    c[name] = value
                    if marker:
                        marker(name, "unproven_synthetic",
                               detail="relaxed compatibility fallback")
        # The embedded jingxuan phone form sends two additional shared-domain
        # page cookies that are not present in the QR jar.  Their values are
        # opaque browser state: import them from a live Cookie header (or set
        # the explicit env overrides) for strict parity; only the relaxed
        # profile gets length-correct placeholders.
        if (getattr(auth, "phone_login_profile", "") == "passport_web"
                and sms_profile == "historical_26"):
            for env_key, name, fallback in (
                ("DY_MONITOR_WEB_ID", "MONITOR_WEB_ID", str(uuid.uuid4())),
                ("DY_UIFID", "UIFID", secrets.token_hex(192)),
            ):
                supplied_value = os.getenv(env_key)
                if name not in c and supplied_value:
                    c[name] = supplied_value
                    marker = getattr(auth, "mark_cookie_source", None)
                    if marker:
                        marker(name, "captured_input", detail=f"env:{env_key}")
                elif name not in c and allow_synthetic \
                        and not getattr(auth, "strict_browser_alignment", False):
                    c[name] = fallback
                    marker = getattr(auth, "mark_cookie_source", None)
                    if marker:
                        marker(name, "unproven_synthetic",
                              detail="historical SMS compatibility fallback")
            # The page writes the first-generation marker before send_code;
            # Chrome changes its value to ``2/<date>/0`` after the challenge
            # window expires (the sms_login capture used that second form).
            c.setdefault("download_guide", DYLoginApi._download_guide("1"))
        # —— passport 登录页自己写的两个 ——
        c.setdefault("gulu_source_res", base64.b64encode(json.dumps(
            {"p_in": secrets.token_hex(32)}, separators=(",", ":")
        ).encode()).decode())
        # In the current Chrome 151 jingxuan flow the two CSRF cookies are
        # written by ``login_guiding_strategy`` after www/ttwid/check.  Keep
        # them out of the first 20-cookie ttwid request and let that response
        # provide the exact values.  The legacy fixture predates this step and
        # still seeds the pair locally.
        if not modern_chrome:
            csrf = c.setdefault("passport_csrf_token", secrets.token_hex(16))
            c.setdefault("passport_csrf_token_default", csrf)
        # QR/check requests use the 48-character initial state.  The embedded
        # passport-web SMS form uses the 32-character state seen in reqid
        # 1765/1874; do not share the QR length with that flow.
        # —— sdk_source_info：与 account_sdk_source_info 同一套 XOR5+hex，
        #    明文是「反自动化探针」的结果清单。键名和顺序照实录解码结果，
        #    别照字面猜 —— `automa_ele` / `console_liad` / `inj_zfb` 这三个
        #    的拼写都不是常规写法（第一版就猜错了这三个）。
        c.setdefault("sdk_source_info", passport_encrypt(json.dumps({
            "automa_ele": "false", "bit_helper": "false",
            "chrome_extension_script": "[]", "console_lied": "false",
            "global_variables": "[]" if modern_chrome else "[\"webdriver\"]",
            "swt_alt": "false", "zn_cap": "false",
            "hok_noti": "false", "inj_zfb": "false",
            "t": DYLoginApi._browser_t(auth, role="cookie"), "bit_protocol": "false",
        }, separators=(",", ":"))))

    @staticmethod
    def _add_client_data_v2(auth):
        """补 `bd_ticket_guard_client_data_v2`。

        结构与 `req_sign` 的被签内容见 `utils.passport.build_client_data_v2_cookie`
        （已用浏览器真值逐字节复现验证）。

        `sec_ts` 的来源：**passport 响应头 `bd-ticket-guard-sec-ts`**。
        响应里的 `access-control-expose-headers` 就明确列了它，所以是
        专门暴露给前端 SDK 读的。
        （不要指望 `/passport/user_info/get_sec_ts/`：匿名态实测返回
        `{"data":null,"message":"success"}`，拿不到值。）

        需要 auth.sec_ts 已经有值，所以第一个 passport 请求发出去之后才补得上。
        """
        sec_ts = getattr(auth, "sec_ts", "") or ""
        if not sec_ts:
            return False
        try:
            from utils.bd_ticket import fetch_server_cert
            ticket_path = "/passport/ticket_guard/get_client_cert/"
            ticket_dtrait = auth.session_dtrait_header(
                ticket_path, aid=6383, origin=HOME_URL)
            cert = fetch_server_cert(
                6383,
                cookie_header(scoped_cookies(auth, "ticket_guard")),
                origin=HOME_URL,
                user_agent=get_profile()["ua"],
                session_dtrait=ticket_dtrait,
                csrf_token="DOWNGRADE",
                ms_token=getattr(auth, "msToken", "") or None,
                referer=os.getenv("DY_PASSPORT_TICKET_GUARD_REFERER")
                or HOME_URL + "/",
            )
            # 返回的是 (cert_pem, sn) 二元组
            server_cert = cert[0] if isinstance(cert, (tuple, list)) else cert
            auth.cookie[CLIENT_DATA_V2_COOKIE] = build_client_data_v2_cookie(
                auth.private_key, sec_ts, server_cert, ts_sign=auth.ts_sign or "")
            auth.cookie_str = "; ".join(f"{k}={v}" for k, v in auth.cookie.items())
            return True
        except Exception as err:
            logger.warning(f"构造 bd_ticket_guard_client_data_v2 失败，跳过: {err}")
            return False

    @staticmethod
    def _harvest_sec_ts(auth, headers, refresh_v2=True):
        """从 passport 响应头收 `bd-ticket-guard-sec-ts`，顺带刷新 v2 Cookie。"""
        v = (headers or {}).get("bd-ticket-guard-sec-ts") or \
            (headers or {}).get("Bd-Ticket-Guard-Sec-Ts")
        if not v:
            return
        if v != getattr(auth, "sec_ts", None):
            auth.sec_ts = v
            if refresh_v2 and not getattr(auth, "_defer_client_data_v2", False):
                DYLoginApi._add_client_data_v2(auth)

    @staticmethod
    def challenge(auth, *, strict: bool = False) -> dict:
        """`POST /passport/web/challenge/` —— 登录页加载后的设备认证。

        2026-08-22 实录时序：get_sec_ts -> ttwid/check -> **challenge** -> get_qrcode。
        我们以前整个跳过了它，直接去取二维码。它有两个副作用是后面要用的：

        1. 响应 Set-Cookie 下发 `passport_csrf_token` / `_default`
           （以前我们是靠 get_qrcode 顺带拿到的，比浏览器晚一步）
        2. 服务端据此把这台设备标记成「已通过 challenge」

        body 是 `sign=<AES-CBC 密文>&sk=<XOR5+hex 的 JS 调用栈>`，共 4445 字节。
        算法已从 async/86383.c2289433.js 还原并用浏览器向量逐字节验证：

        - key = SHA256(userAgent)，IV = key 后 16 字节
        - plaintext = btoa(JSON.stringify(collectFingerprintInfo()))
        - AES-256-CBC + PKCS#7，密文用 Base64URL（保留 `=` padding）
        - sk = XOR5(UTF8(encodeURIComponent(getStackError()))) 的 hex

        字体/canvas/WebGL 属于设备采集值，保存在 challenge_profile.json；运行时
        只读该指纹档案并纯算密文。
        """
        from utils.challenge_sign import build_challenge_body
        body = build_challenge_body()
        data = dict(urllib.parse.parse_qsl(body, keep_blank_values=True))
        # 实录 query 与 check_qrconnect 的差异：ts 之后是 request_host / skip_c，
        # 且**没有 p_ui**。位置错了 sign 的前 10 名窗口就可能换人。
        params = DYLoginApi._sdk_params(
            auth,
            {"request_host": urllib.parse.quote(HOME_URL, safe=""), "skip_c": "1"},
            data=data, device_fp=True, with_p_ui=False, with_request_host=False)
        params.with_a_bogus(data, host="login.douyin.com")
        resp = auth.request(
            "POST", LOGIN_URL + "/passport/web/challenge/",
            headers=headers_with_cookie(
                DYLoginApi._passport_headers(
                    auth, form=True, api="/passport/web/challenge/",
                    strict_dtrait=bool(strict)).get(),
                scoped_cookies(auth, "challenge")),
            params=params.get(), data=body,
            verify=False, timeout=25)
        merge_set_cookies(auth, resp.cookies.get_dict())
        DYLoginApi._harvest_sec_ts(auth, resp.headers)
        try:
            res = resp.json()
        except Exception:
            return {"raw": resp.text[:200], "status": resp.status_code}
        DYLoginApi._apply_challenge_template(auth, res, strict=bool(strict))
        return res

    @staticmethod
    def _apply_challenge_template(auth, res, *, strict: bool = False):
        """跑 challenge 下发的 template，把 `p_in` / `e_in` 写回 Cookie。

        challenge 的响应不只是「成功」——`data.template` 是一段 77KB 的 JS
        （UMD 模块 `__p_ch`），浏览器要执行它才算真正交作业，产出：

        - `p_in` -> Cookie `gulu_source_res` = base64({"p_in": <sha256>})
        - `e_in` -> Cookie `sdk_source_info` 的明文（XOR5+hex 之前）

        这两个 Cookie 我们之前都是**伪造**的：`p_in` 用随机 hex、
        `e_in` 靠猜键名（还猜错了 `automa_ele`/`console_liad`/`inj_zfb` 三个）。
        等于 challenge 请求发了、响应收了，但那段 JS 从没跑过 ——
        而服务端下发 template 就是要看这个结果的。

        浏览器专属探针在 Node 补环境中可能不会返回；对这些稳定的
        “未检测到”字段使用页面默认值。真正无法执行模板或没有产出
        ``p_in``/``e_in`` 时，严格模式仍然拒绝继续。
        """
        data = (res or {}).get("data") or {}
        tpl = data.get("template")
        # ``passportiv`` is the server challenge material used by the page to
        # derive ``bit_env``.  It is not part of the template output and must
        # be consumed before the request returns so every subsequent passport
        # request carries the same cookie as Chrome.
        passportiv = data.get("passportiv")
        if passportiv:
            try:
                from utils.challenge_sign import build_bit_env
                auth.cookie["bit_env"] = build_bit_env(passportiv)
                marker = getattr(auth, "mark_cookie_source", None)
                if marker:
                    marker("bit_env", "local_pure_conditional",
                           detail="HTTP challenge passportiv + local AES-CBC")
            except Exception as err:
                logger.warning(f"根据 challenge passportiv 生成 bit_env 失败: {err}")
                if strict:
                    raise RuntimeError(
                        "严格登录要求 challenge passportiv 可生成 bit_env"
                    ) from err
        if not tpl:
            if strict:
                raise RuntimeError(
                    "严格短信登录的 challenge 响应缺少 data.template；"
                    "拒绝使用伪造 p_in/e_in"
                )
            return False
        try:
            from utils.challenge_template import run_template
            out = run_template(tpl)
        except Exception as err:
            logger.warning(f"跑 challenge template 失败，沿用伪造值: {err}")
            if strict:
                raise RuntimeError(
                    "严格短信登录的 challenge template 执行失败"
                ) from err
            return False
        if not out or not out.get("p_in"):
            logger.warning("challenge template 没产出 p_in，沿用伪造值")
            if strict:
                raise RuntimeError(
                    "严格短信登录的 challenge template 未产出 p_in"
                )
            return False
        e_in = out.get("e_in")
        if not isinstance(e_in, dict):
            e_in = {}
        if strict:
            p_in = str(out.get("p_in") or "")
            if not re.fullmatch(r"[0-9a-fA-F]{64}", p_in):
                raise RuntimeError(
                    "严格短信登录的 challenge template p_in 不是 64 位 sha256 hex"
                )
            required_probe_keys = {
                "automa_ele", "bit_helper", "chrome_extension_script",
                "console_lied", "global_variables", "swt_alt", "zn_cap",
                "hok_noti", "inj_zfb", "t", "bit_protocol",
            }
            # The shipped challenge bundle returns only the probes it can
            # observe.  In the browserless Node realm the four extension /
            # automation probes (automa_ele, bit_helper,
            # chrome_extension_script, hok_noti) are legitimately absent;
            # they are not a failed challenge.  Their Chrome values are the
            # stable negative defaults used by the page serializer below.
            # Keep rejecting a completely empty e_in, which indicates that
            # the template did not execute its probe stage at all.
            if not e_in:
                raise RuntimeError(
                    "严格短信登录的 challenge template 未产出 e_in 探针"
                )
            missing = sorted(required_probe_keys - set(e_in))
            if missing:
                logger.warning(
                    "challenge template 在无浏览器补环境中未返回 "
                    f"{missing}；将使用页面默认的非自动化探针值继续"
                )
        auth.cookie["gulu_source_res"] = base64.b64encode(json.dumps(
            {"p_in": out["p_in"]}, separators=(",", ":")).encode()).decode()
        if isinstance(e_in, dict):
            # The template's probe result is partial in the Node fallback:
            # browser execution still serializes the complete 11-key object.
            # Keep the browser key order/types and overlay any values the
            # template did return.  In particular, omitting these defaults
            # shrinks sdk_source_info from the browser's 472 chars to 288.
            current_chrome = _passport_profile("DY_PASSPORT_COOKIE_PROFILE") \
                in ("chrome_current", "chrome_current_early")
            browser_probe = {
                "automa_ele": "false",
                "bit_helper": "false",
                "chrome_extension_script": "[]",
                "console_lied": "false",
                "global_variables": "[]" if current_chrome else "[\"webdriver\"]",
                "swt_alt": "false",
                "zn_cap": "false",
                "hok_noti": "false",
                "inj_zfb": "false",
                "t": DYLoginApi._browser_t(auth, role="cookie"),
                "bit_protocol": "false",
            }
            browser_probe.update(e_in)
            # The old fixture recorded a webdriver marker.  The current live
            # Chrome capture records an empty list; do not force the old value
            # into the current profile because it changes sdk_source_info from
            # 472 to 498 bytes.
            browser_probe["global_variables"] = "[]" if current_chrome else "[\"webdriver\"]"
            browser_probe.pop("console_liad", None)
            browser_probe["console_lied"] = "false"
            auth.cookie["sdk_source_info"] = passport_encrypt(
                json.dumps(browser_probe, separators=(",", ":"), ensure_ascii=False))
        auth.cookie_str = "; ".join(f"{k}={v}" for k, v in auth.cookie.items())
        logger.info("challenge template 已执行：p_in=%s... e_in %d 项"
                    % (out["p_in"][:16], len(e_in or {})))
        return True

    @staticmethod
    def _browser_t(auth, role="query") -> str:
        """反自动化探针里的 `t`，13 位数字。

        实录里同一次会话的两处取值是
        `8917524837871`（cookie `sdk_source_info`）与
        `4576524837871`（query `account_sdk_source_info.browser.t`）——
        **后 9 位完全相同**。所以它是「4 位随机 + 会话内固定的 9 位」，
        不是两个独立随机数。两处必须共用同一个后缀，否则一比就露。
        """
        # Chrome uses one stable value for the encrypted query probe and a
        # second stable value for the cookie probe.  They share the same
        # nine-digit session suffix, but the four-digit prefixes are allowed
        # to differ (the live capture has 6117... in
        # ``account_sdk_source_info`` and 3637... in ``sdk_source_info``).
        # The old single fixed variable remains an explicit override for
        # fixture replay; role-specific variables take precedence when a
        # capture needs both values reproduced independently.
        role = "cookie" if str(role).lower() == "cookie" else "query"
        fixed = (os.getenv("DY_PASSPORT_FIXED_BROWSER_T_COOKIE")
                 if role == "cookie" else
                 os.getenv("DY_PASSPORT_FIXED_BROWSER_T_QUERY"))
        fixed = fixed or os.getenv("DY_PASSPORT_FIXED_BROWSER_T")
        if fixed:
            if not fixed.isdigit() or len(fixed) != 13:
                raise ValueError("DY_PASSPORT_FIXED_BROWSER_T must be 13 digits")
            return fixed
        if auth is None:
            suffix = "%09d" % secrets.randbelow(10 ** 9)
            return "%04d%s" % (secrets.randbelow(10 ** 4), suffix)
        if not getattr(auth, "_t_suffix", None):
            auth._t_suffix = "%09d" % secrets.randbelow(10 ** 9)
        attr = "_t_cookie" if role == "cookie" else "_t_query"
        if not getattr(auth, attr, None):
            setattr(auth, attr, "%04d%s" % (
                secrets.randbelow(10 ** 4), auth._t_suffix))
        return getattr(auth, attr)

    @staticmethod
    def _sdk_source_info(auth=None, page_url: str = None) -> str:
        """`account_sdk_source_info`：硬件指纹 JSON 经 passport 的 XOR 5 + hex 编码。

        2026-08-22 用真实登录实录校准：原实现只发 11 个叶子字段（明文 309 字符），
        浏览器发 30 个（1694 hex / 847 明文）。补齐了三块：

        - `automation`：反自动化探针的结果，正常浏览器全是 0
        - `performance`：`performance.timeOrigin` / `usedJSHeapSize` +
          导航计时（`guleStart`/`guleDuration` 是字节自己加的埋点）
        - `browser`：`t` / `bit_protocol` / `bit_helper`

        另修掉一处**自相矛盾**：窗口尺寸原来写死 `h-635` / `w-1280`
        （2560x1440 的屏算出 1280x805 的窗口），而同一个 profile 里
        `geo` 早就按实录算好了 1215 / 1392。两边必须同源，否则
        query 报 2560 宽的屏、这里报 1280 宽的窗，一比就露。
        """
        # This is a page-session measurement, not a per-request nonce.  The
        # browser reuses the same encrypted value for challenge, send_code,
        # and sms_login; recomputing it would change timeOrigin/browser.t and
        # therefore also invalidate passport ``sign``/``a_bogus``.  Keep the
        # optional page_url argument usable for standalone callers, but cache
        # the normal auth-bound value for the lifetime of one login page.
        if auth is not None and page_url is None:
            cached = getattr(auth, "_passport_sdk_source_info", "")
            if cached:
                return cached

        p = get_profile()
        cookie_profile = _passport_profile("DY_PASSPORT_COOKIE_PROFILE")
        current_chrome = cookie_profile == "chrome_current"
        current_early = cookie_profile == "chrome_current_early"
        # geo = (w, innerH, w, outerH, w, availH, w, h)，与 a_bogus 用的是同一份
        inner_w, inner_h, outer_w, outer_h = p["geo"][0], p["geo"][1], p["geo"][2], p["geo"][3]
        fixed_now_ms = (
            os.getenv("DY_PASSPORT_FIXED_SOURCE_TIME_MS")
            or os.getenv("DY_FIXED_TIMESTAMP_MS")
        )
        now_ms = float(fixed_now_ms) if fixed_now_ms else time.time() * 1000
        def _number_env(name, default):
            value = os.getenv(name)
            if value in (None, ""):
                return default
            try:
                # Chrome's JSON can expose an integral timeOrigin but
                # fractional performance marks. Preserve that distinction:
                # forcing every override through float adds a spurious `.0`
                # and changes the encrypted account_sdk_source_info bytes.
                if re.fullmatch(r"[-+]?\d+", value):
                    return int(value)
                return float(value)
            except (TypeError, ValueError):
                return default

        def _int_env(name, default):
            value = os.getenv(name)
            if value in (None, ""):
                return default
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        # These are browser measurements, not cryptographic secrets.  Keeping
        # them overrideable lets a captured Chrome run be replayed byte-for-
        # byte while retaining sensible defaults for ordinary use.
        time_origin = _number_env(
            "DY_PASSPORT_FIXED_TIME_ORIGIN_MS",
            round(now_ms - random.uniform(3000, 60000), 1))
        heap_size = _int_env(
            "DY_PASSPORT_FIXED_USED_JS_HEAP_SIZE",
            (472537551 if current_chrome else
             332892008 if current_early else
             random.randint(100_000_000, 140_000_000)))
        decoded_size = _int_env(
            "DY_PASSPORT_FIXED_DECODED_BODY_SIZE",
            (968454 if current_chrome else
             1027831 if current_early else
             random.randint(1_000_000, 1_200_000)))
        gule_start = _number_env(
            "DY_PASSPORT_FIXED_GULE_START",
            (610.8999999761581 if current_chrome else
             578.6999999880791 if current_early else
             520.2999999821186))
        gule_duration = _number_env(
            "DY_PASSPORT_FIXED_GULE_DURATION",
            ("none" if current_chrome else
             12.200000017881393 if current_early else
             8.099999994039536))
        # The live login page's navigation timing points to the root document
        # even when the modal is opened from /jingxuan.
        default_page = HOME_URL + "/?recommend=1"
        fixed_page = os.getenv("DY_PASSPORT_FIXED_PAGE_URL")
        info = {
            "hardwareConcurrency": int(p["cpu_core_num"]),
            "webdriver": False, "chromedriver": False, "shelldriver": False,
            "plugins": 5,
            "innerHeight": inner_h, "innerWidth": inner_w,
            "outerHeight": outer_h, "outerWidth": outer_w,
            "webgl": {"vendor": p["webgl_vendor"], "renderer": p["webgl_renderer"]},
            # 实录里全 0 —— 这几项是自动化痕迹探针，真人浏览器就是 0
            "automation": {"s": "00000000", "c": "0000", "p": "0000000",
                           "s1": "00000000", "c1": "0000", "p1": "0"},
            "performance": {
                # 页面打开时刻：取当前时间往前推几秒，保留一位小数。
                # Chrome 的 performance.timeOrigin 在实录里是浮点毫秒值；
                # 强制转 int 会让 account_sdk_source_info 少一个小数段，
                # 进而出现可见的密文长度差异。
                "timeOrigin": time_origin,
                "usedJSHeapSize": heap_size,
                "navigationTiming": {
                    "decodedBodySize": decoded_size,
                    "entryType": "navigation",
                    "initiatorType": "navigation",
                    "name": page_url or fixed_page or default_page,
                    "renderBlockingStatus": "non-blocking",
                    "serverTiming": (
                        os.getenv("DY_PASSPORT_FIXED_SERVER_TIMING")
                        or "cdn-cache,edge,origin,inner,tt_agw"
                        if (current_chrome or current_early)
                        else "inner,tt_agw,cdn-cache,edge,origin"
                    ),
                    # These values originate from browser performance marks;
                    # V8's floating-point tails are visible in the encrypted
                    # field, so retain a comparable tail instead of short
                    # decimal literals that change the payload length.
                    "guleStart": gule_start,
                    "guleDuration": gule_duration,
                },
            },
            "browser": {"t": DYLoginApi._browser_t(auth) if auth is not None
                        else DYLoginApi._browser_t(auth, role="query"),
                        "bit_protocol": "false", "bit_helper": False},
        }
        value = passport_encrypt(json.dumps(info, ensure_ascii=False,
                                            separators=(",", ":")))
        if auth is not None and page_url is None:
            auth._passport_sdk_source_info = value
        return value

    @staticmethod
    def _sdk_ts(now=None) -> str:
        """passport 的 `ts`：**当天 UTC 12:00** 的秒级时间戳。

        对应 SDK 里的 `Date.UTC(y, m, d, 12, 0, 0, 0) / 1000`。

        早先写成 `time() // 43200 * 43200`（最近的 12 小时边界），只在 UTC 12:00
        之后才和 SDK 一致；UTC 12:00 之前会算成当天 00:00，和浏览器差 12 小时。
        抓包那一刻恰好落在相同的区间，所以这个错一直没暴露。
        """
        if now is None:
            fixed = os.getenv("DY_PASSPORT_FIXED_TS") or os.getenv("DY_FIXED_TIMESTAMP")
            now = float(fixed) if fixed else time.time()
        d = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
        noon = datetime.datetime(d.year, d.month, d.day, 12, 0, 0,
                                 tzinfo=datetime.timezone.utc)
        return str(int(noon.timestamp()))

    @staticmethod
    def _aid_sign(path: str, ts: str, aid: str = "6383") -> str:
        """算 `x-tt-passport-aid-sign`，还原自 async/28872.*.js 的 C() 拦截器。

        ```js
        ts   = Date.UTC(y,m,d,12,0,0)/1000
        prk  = hmac_sha256(ts, appKey)                 // HKDF-extract，salt=ts
        okm  = hmac_sha256(unhex(prk), [1])            // HKDF-expand，info 空、L=32
        sign = hmac_sha256(okm, `aid=${aid}&path=${path}&ts=${ts}`)
        ```

        `path` 取 URL 去掉 query 的部分；SDK 里还有个 `P()` 会给 sso 域补
        `/passport/sso` 前缀，我们只打 `/passport/web/...`，本就以 /passport 开头，
        原样使用即可。

        拿 2026-08-16 实录对账，8 条请求的 aid-sign 全部逐字节一致。
        """
        prk = hmac.new(ts.encode(), PASSPORT_APP_KEY.encode(), hashlib.sha256).hexdigest()
        okm = hmac.new(bytes.fromhex(prk), b"\x01", hashlib.sha256).digest()
        msg = "aid=%s&path=%s&ts=%s" % (aid, path, ts)
        return hmac.new(okm, msg.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _passport_sign(query: dict, data: dict = None):
        """算 passport 的 `sign` / `qs`，还原自 async/28872.*.js。

        ```js
        l = (e, t=-1) => { let r = Object.keys(e).sort(); if (t>=0) r.splice(t);
                           return {str: r.map(k => `${k}=${e[k]}`).join("&"), arr: r} }
        h = (query, data, appKey) => {
              let {str:i, arr:o} = l(query, 10), {str:s} = l(data);
              return {sign: sha256(`${i}&${s}&app_key=${appKey}`), qs: xor5hex(o.join(","))} }
        ```

        拿 2026-08-16 的登出态实录对账，challenge / get_qrcode / check_qrconnect
        共 8 条请求的 sign 与 qs **全部逐字节一致**。

        早先版本没实现这两个字段，理由是「不带也能拿到二维码」—— 那是
        `get_qrcode` 宽松，`check_qrconnect` 会因此返回 `error_code=7`
        「访问太频繁」，看起来像限频，实际是签名缺失被兜底话术挡回来。
        """
        signable = {k: v for k, v in query.items() if k not in SIGN_EXCLUDE}
        keys = sorted(signable)[:SIGN_KEY_LIMIT]
        qstr = "&".join("%s=%s" % (k, signable[k]) for k in keys)
        body = data or {}
        bstr = "&".join("%s=%s" % (k, body[k]) for k in sorted(body))
        plain = "%s&%s&app_key=%s" % (qstr, bstr, PASSPORT_APP_KEY)
        sign = hashlib.sha256(plain.encode("utf-8")).hexdigest()
        return sign, passport_encrypt(",".join(keys))

    @staticmethod
    def _sdk_params(auth, extra=None, data=None, device_fp=False,
                    with_p_ui=True, with_request_host=True,
                    with_ms_token=True) -> Params:
        """登录接口的公共 query，字段与顺序对齐 2026-08-22 完整登录实录。

        :param data: 该请求的 body（POST 时必传）—— `sign` 是把 query 和 body
            一起签的，漏传 body 算出来的签名是错的。
        :param device_fp: 是否带 `p_ca` / `p_ca_real` 以及当前 passport
            版本要求的 `fp` / `verifyFp`。**按接口取值，不是公共字段**：

            | 接口 | 带 |
            | --- | --- |
            | `challenge` / `check_qrconnect` | 是 |
            | `get_qrcode` / `web_record_status` / `token/beat` | 否 |

            2026-08-29 Chrome 151 / passport 3.4.4
            重新抓到的真值是：`challenge` 与 `check_qrconnect` 都带
            `p_ca,p_ca_real,fp,verifyFp`（顺序固定），`get_qrcode` 不带。
            旧的 `passport_capture.json` 是 3.1.3 实录，不能继续作为当前版本基线。
        """
        params = Params()
        for key, value in PASSPORT_SDK.items():
            params.add_param(key, value)
        params.add_param("aid", "6383")
        params.add_param("language", "zh")
        params.add_param("account_app_language", "zh-CN")
        # ts 是当天 UTC 12:00，不是当前秒（见 _sdk_ts）
        params.add_param("ts", DYLoginApi._sdk_ts())
        for key, value in (extra or {}).items():
            params.add_param(key, value)
        # p_ui 不是所有接口都有：challenge 就没有（实录 29 项里没它），
        # get_qrcode / check_qrconnect 有。
        if with_p_ui:
            params.add_param("p_ui", PASSPORT_SDK_TAIL["p_ui"])
        if device_fp:
            params.add_param("p_ca", PASSPORT_SDK_TAIL["p_ca"])
            params.add_param("p_ca_real", PASSPORT_SDK_TAIL["p_ca_real"])
            # 3.4.2 在扫码前后都把主站生成的 s_v_web_id 同时映射为
            # fp/verifyFp；缺这两个字段时，扫码前仍可能返回 new/scanned，
            # 但扫码后的凭证校验会被兜底成 error_code=7。
            fp = auth.cookie.get("s_v_web_id") or generate_s_v_web_id()
            auth.cookie.setdefault("s_v_web_id", fp)
            params.add_param("fp", fp)
            params.add_param("verifyFp", fp)
        params.add_param("account_sdk_source", PASSPORT_SDK_TAIL["account_sdk_source"])
        params.add_param("account_sdk_source_info", DYLoginApi._sdk_source_info(auth))
        for key in ("p_js_v", "p_js_t", "p_zt", "p_ver", "p_ver_real"):
            params.add_param(key, PASSPORT_SDK_TAIL[key])
        # request_host 的值本身就是 URL 编码过的，发出去会再编一次（双重编码）。
        # challenge 把它排在 ts 之后（由调用方经 extra 传入），所以那里要关掉
        # 这个固定位置，否则位置对不上。
        if with_request_host:
            params.add_param("request_host", urllib.parse.quote(HOME_URL, safe=""))
        params.add_param("p_bd", PASSPORT_SDK_TAIL["p_bd"])
        fixed_p_ts = os.getenv("DY_PASSPORT_FIXED_P_TS") or os.getenv("DY_FIXED_TIMESTAMP_MS")
        params.add_param(
            "p_ts",
            str(int(fixed_p_ts)) if fixed_p_ts else str(int(time.time() * 1000)),
        )
        p_no = os.getenv("DY_PASSPORT_FIXED_P_NO") or secrets.token_hex(32)
        params.add_param("p_no", p_no)
        biz_trace_id = (
            auth.cookie.get("biz_trace_id")
            or os.getenv("DY_PASSPORT_FIXED_BIZ_TRACE_ID")
            or secrets.token_hex(4)
        )
        params.add_param("biz_trace_id", biz_trace_id)
        params.add_param("device_platform", "web_app")
        # 顺序照实录：sign / qs 紧跟 device_platform，msToken 和 a_bogus 在其后，
        # 且这两个不参与签名（见 SIGN_EXCLUDE）
        sign, qs = DYLoginApi._passport_sign(params.get(), data)
        params.add_param("sign", sign)
        params.add_param("qs", qs)
        if with_ms_token:
            params.add_param("msToken", auth.msToken)
        return params

    @staticmethod
    def _passport_headers(auth, form=False, api="", strict_dtrait=False,
                          body_length=None, wire_accept_encoding=False):
        """passport 请求头，字段与顺序照 2026-08-22 完整登录实录。

        **不能沿用 HeaderBuilder 的默认头**：主站 aweme XHR 那套与这里不同，
        域不同头就不同，得分开建。

        ⚠️ 2026-08-29 Chrome 151 重抓：passport 3.4.4 的 JS 视图明确包含
        `web-sdk-version: 1`，且网络层会再补 cookie/origin/fetch 等头。分清两种
        视图就明白了：

        - `headers_js`（CDP `requestWillBeSent`）：只有页面 JS 设的头
        - `headers_wire`：真正上线的头，多出 `cookie` / `origin` / `priority` /
          `accept-encoding` / `accept-language` / `sec-fetch-*` / `content-length`
          这些**浏览器网络层自己补的**

        旧版抓包只存了部分 JS 视图，不能拿它当当前全集
        会把版本升级后的头和参数误判成「我们多发的」。本次 Chrome 151 短信实录
        显示 passport 业务请求带 `web-sdk-version: 1`，但不带 `sec-ch-ua*`、
        `cache-control` 或 `pragma`；扫码校验的 query 还新增 `fp/verifyFp`。

        下面的顺序照 `passport_capture.json` 的 JS 视图（app 设的头之间的相对
        顺序只有它保得住；wire 视图被 CDP 按字母序排过，顺序信息已丢失）：

            web-sdk-version, x-tt-session-dtrait, referer, x-tt-passport-aid-sign,
            x-tt-passport-csrf-token,
            x-tt-passport-trace-id, user-agent, accept, content-type,
            x-tt-passport-verify-portrait

        `x-tt-passport-verify-portrait` 一度被判定为「浏览器不发」并去掉，
        依据是拦截器里 `window._verifyPortraitId` 的取值条件。实录推翻了这个
        判断：所有 passport 请求都带着它。值由 `bootstrap_auth` 生成。

        ``DY_PASSPORT_HEADER_PROFILE=chrome4468`` selects the older controlled
        capture; the default ``chrome_current`` is the current Chrome 151 SMS
        shape above.  Both omit ``sec-ch-ua*``, ``cache-control`` and ``pragma``.
        """
        profile = get_profile()
        header_profile = _passport_profile("DY_PASSPORT_HEADER_PROFILE")
        # The live Chrome 151 SMS requests (reqid=608/735) have the same
        # controlled header set/order as the earlier reqid=4468 capture: no
        # sec-ch-ua*, cache-control or pragma on passport XHRs.  Keep the old
        # cURL profile untouched.
        # Both profiles intentionally omit Chrome client-hint/cache headers;
        # this is what the current Chrome 151 passport captures show.
        chrome4468 = header_profile == "chrome4468"
        chrome_current = header_profile in ("chrome_current", "chrome_current_early")
        headers = Header()
        # 当前 passport SDK（3.4.4）通过 CORS 预检声明并在实际请求中发送
        # 这个头。旧 3.1.3 实录没有记录它，不能拿旧实录覆盖新版本真值。
        headers.set_header("web-sdk-version", "1")
        # Chrome 151 的 QR/bootstrap 请求保留 sec-ch-ua*；短信表单不带。
        # `api` 是调用方传入的完整 passport pathname，可据此选择协议分支。
        qr_headers = any(
            api.endswith(path)
            for path in ("/passport/web/challenge/",
                         "/passport/web/get_qrcode/",
                         "/passport/web/check_qrconnect/")
        )
        if qr_headers:
            headers.set_header("sec-ch-ua-platform", profile["sec_ch_ua_platform"])
        dtrait = (auth.session_dtrait_header(
            api, aid=6383, origin=HOME_URL, strict=strict_dtrait)
            if api else None)
        if strict_dtrait and len(dtrait or "") != 820:
            raise RuntimeError(
                "x-tt-session-dtrait 未达到 Chrome 短信实录的 820 字节，"
                f"当前 {len(dtrait or '')} 字节，已拒绝发送"
            )
        if dtrait:
            headers.set_header("x-tt-session-dtrait", dtrait)
        # 登录接口在 login.douyin.com，但页面在主站，所以 referer 指主站
        headers.set_header("referer", HOME_URL + "/")
        if qr_headers:
            headers.set_header("sec-ch-ua", profile["sec_ch_ua"])
        if api:
            headers.set_header("x-tt-passport-aid-sign",
                               DYLoginApi._aid_sign(api, DYLoginApi._sdk_ts()))
        csrf = auth.cookie.get("passport_csrf_token") or auth.cookie.get("passport_csrf_token_default")
        # 实录：还没拿到 token 的那个请求（challenge）**发的是空串**，不是不发。
        # 「字段值为空」和「字段不存在」是两回事，后者才是风控特征。
        if qr_headers:
            headers.set_header("sec-ch-ua-mobile", "?0")
        headers.set_header("x-tt-passport-csrf-token", csrf or "")
        trace = auth.cookie.get("biz_trace_id")
        if trace:
            headers.set_header("x-tt-passport-trace-id", trace)
        headers.set_header("user-agent", profile["ua"])
        headers.set_header("accept", "application/json, text/javascript")
        if form:
            headers.set_header("content-type", "application/x-www-form-urlencoded")
        portrait = getattr(auth, "verify_portrait", "")
        if portrait:
            headers.set_header("x-tt-passport-verify-portrait", portrait)
        # 浏览器网络层补的那批。curl_cffi 用了 default_headers=False（见
        # utils/http_client.py），这些不会自动加，得自己发。短信表单还要
        # 显式给出 accept-encoding/content-length：只有这样才能把它们放在
        # Chrome 151 实录的位置（portrait -> encoding -> language -> length
        # -> cookie -> origin），并阻止 libcurl 把 accept-encoding 自动前插。
        if wire_accept_encoding:
            headers.set_header("accept-encoding", "gzip, deflate, br, zstd")
        headers.set_header("accept-language", "zh-CN,zh;q=0.9")
        if body_length is not None:
            headers.set_header("content-length", str(int(body_length)))
        headers.set_header("origin", HOME_URL)
        headers.set_header("priority", "u=1, i")
        headers.set_header("sec-fetch-dest", "empty")
        headers.set_header("sec-fetch-mode", "cors")
        # 页面在 www.douyin.com、接口在 login.douyin.com：同站不同子域
        headers.set_header("sec-fetch-site", "same-site")
        # 这里**不发** bd-ticket-guard-* ——实录确认浏览器在所有 passport 请求上
        # 都不带这三个头，它是另走 /passport/ticket_guard/get_client_cert/
        # 拿证书的（见 utils.bd_ticket.fetch_server_cert）。以前顺手挂在登录
        # 请求头上，属于我们自己加的东西。
        ordered = Header()
        if qr_headers and chrome_current:
            order = PASSPORT_HEADER_ORDER_CHROME_CURRENT_QR
        elif chrome4468:
            order = PASSPORT_HEADER_ORDER_CHROME4468
        elif chrome_current:
            order = PASSPORT_HEADER_ORDER_CHROME_CURRENT
        else:
            order = PASSPORT_HEADER_ORDER
        for name in order:
            if name in headers.headers:
                ordered.set_header(name, headers.headers[name])
        return ordered

    # ---------- sso 域的 gfkadpd 拦截页 ----------
    @staticmethod
    def _solve_gfkadpd(auth, resp) -> bool:
        """sso 域首次访问会返回一个只做 `document.cookie=gfkadpd=<e>,<t>` 再刷新的拦截页。

        脚本里两个数字是明文的，取出来直接补上 Cookie 即可，无需执行 JS。
        返回是否补上了 Cookie（补上了就该重试请求）。
        """
        text = resp.text or ""
        if "gfkadpd" not in text:
            return False
        m = re.search(r'var\s+e\s*=\s*"(\d+)"\s*,\s*t\s*=\s*"(\d+)"', text)
        if not m:
            return False
        auth.cookie["gfkadpd"] = f"{m.group(1)},{m.group(2)}"
        auth.cookie_str = "; ".join(f"{k}={v}" for k, v in auth.cookie.items())
        logger.info(f"已补 gfkadpd Cookie: {auth.cookie['gfkadpd']}")
        return True

    def _passport_get(self, auth, api, params_builder):
        """passport GET 请求，遇到 gfkadpd 拦截页自动补 Cookie 重试一次。"""
        for attempt in range(2):
            params = params_builder()
            params.with_a_bogus(host="login.douyin.com")
            resp = auth.request(
                                "GET", self.base_url + api,
                                headers=headers_with_cookie(
                                    self._passport_headers(
                                        auth, api="/passport/web/" + api).get(),
                                    scoped_cookies(auth, "qr" if api == "get_qrcode/" else "login")),
                                params=params.get(), verify=False, timeout=20)
            set_cookies = resp.cookies.get_dict()
            merge_set_cookies(auth, set_cookies)
            apply_ticket_guard(auth, resp.headers, set_cookies)
            DYLoginApi._harvest_sec_ts(auth, resp.headers)
            if resp.text.lstrip().startswith("{"):
                res = resp.json()
                self._raise_if_blocked(api, res)
                return res
            if attempt == 0 and self._solve_gfkadpd(auth, resp):
                continue
            raise RuntimeError(
                f"{api} 返回的不是 JSON（多为 gfkadpd 拦截页或缺少匿名 Cookie）。"
                f"HTTP {resp.status_code}，前 120 字：{resp.text[:120]!r}")

    @staticmethod
    def _raise_if_blocked(api, res):
        """把 passport 的风控错误码翻译成可读异常。"""
        data = res.get("data") or {}
        code = data.get("error_code")
        if code in (0, None):
            return
        desc = data.get("description") or res.get("message") or ""
        if code == 4031:
            raise RuntimeError(
                f"{api} 返回 4031「网站存在安全风险」。这不是 acrawler / 设备凭据的问题："
                f"实测把请求域写成 www.douyin.com、或 passport SDK 版本号对不上时必得此码，"
                f"真实浏览器发同样的请求也一样。请确认走的是 {LOGIN_URL} 且 "
                f"passport_jssdk_version/type 与登录页一致。原始描述：{desc}")
        raise RuntimeError(f"{api} 失败 error_code={code} {desc}")

    # ---------- 安全时间戳 ----------
    @staticmethod
    def get_sec_ts(auth) -> dict:
        """`/passport/user_info/get_sec_ts/`，登录页加载时浏览器会先打这个。

        ⚠️ 2026-08-22 更正两点（实录 reqid=282）：

        1. **`sec_ts` 在响应头 `bd-ticket-guard-sec-ts` 里，不在 body**。
           body 只有 `{"data":null,"message":"success"}` —— 以前照 body 取，
           自然永远是空，还误以为"匿名态拿不到"。
        2. csrf 头发的是**字面量 `DOWNGRADE`**，不是现算的 token；
           而且不发 `sec-ch-ua*`，发的是 `origin`/`priority`/`sec-fetch-*`
           （`sec-fetch-site: same-origin`，因为这个接口在 www 本域）。

        顺带把取到的 sec_ts 落到 `auth.sec_ts` 并刷新 client_data_v2 Cookie。
        """
        profile = get_profile()
        # Chrome's request path contains the mssdk token and a_bogus.  They
        # are not part of the form body or passport sign, but omitting them
        # changes both the URL bytes and the server's risk input.
        query = {
            "aid": "6383",
            "is_from_ttaccountsdk": "1",
            "msToken": auth.msToken,
        }
        query["a_bogus"] = generate_a_bogus(
            urllib.parse.urlencode(query), host="www.douyin.com"
        )
        headers = {
            "referer": HOME_URL + "/user/self",
            "user-agent": profile["ua"],
            "accept": "application/json",
            "x-secsdk-csrf-token": "DOWNGRADE",
            "content-type": "application/x-www-form-urlencoded",
            "accept-language": "zh-CN,zh;q=0.9",
            "origin": HOME_URL,
            "priority": "u=1, i",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        resp = auth.request("POST", HOME_URL + "/passport/user_info/get_sec_ts/",
                             headers=headers_with_cookie(headers, scoped_cookies(auth, "www_bootstrap")),
                             params=query,
                             data=urllib.parse.urlencode({
                                 "aid": query["aid"],
                                 "is_from_ttaccountsdk": query["is_from_ttaccountsdk"],
                             }),
                             verify=False, timeout=20)
        merge_set_cookies(auth, resp.cookies.get_dict())
        # Chrome does not fetch ticket-guard client cert until after the
        # login-domain ttwid/check request.  Harvest sec_ts now, but defer the
        # v2-cookie fetch to bootstrap_auth so request order matches.
        DYLoginApi._harvest_sec_ts(auth, resp.headers, refresh_v2=False)
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text[:200], "status": resp.status_code}

    # ---------- 扫码登录 ----------
    def get_qrcode(self, auth) -> dict:
        """取登录二维码，返回 {token, qrcode_index_url, ...}。"""
        # The first Chrome 151 get_qrcode omits p_ca/fp.  Once a check has
        # returned expired, the page-side SDK refresh uses the full device-fp
        # tuple (p_ca, p_ca_real, fp, verifyFp) and the refreshed Cookie jar.
        cookie_profile = _passport_profile("DY_PASSPORT_COOKIE_PROFILE")
        refreshed = (cookie_profile in ("chrome_current", "chrome_current_early")
                     and getattr(auth, "_qr_refresh_ready", False))
        result = self._passport_get(
            auth, "get_qrcode/",
            lambda: self._sdk_params(auth, {
                "next": HOME_URL,
                "need_short_url": "true",
                "need_logo": "false",
                "is_new_login": "1",
                "is_from_iesaccountsaas": "1",
            }, device_fp=refreshed),
        )
        if cookie_profile == "chrome_current_early":
            # In this lifecycle the page performs ticket_guard/get_client_cert
            # immediately after get_qrcode.  Build v2 now so the first
            # check_qrconnect carries the same 22-cookie jar as Chrome.
            if getattr(auth, "_defer_client_data_v2", False):
                try:
                    if not self._add_client_data_v2(auth):
                        logger.warning("get_qrcode 后未能生成 bd_ticket_guard_client_data_v2")
                except Exception as err:
                    logger.warning(f"get_qrcode 后初始化 client_data_v2 失败: {err}")
                auth._defer_client_data_v2 = False
            # The first get_qrcode is the boundary after which ticket-guard
            # cookies are present on check_qrconnect in this lifecycle.
            auth._qr_started = True
        return result

    def check_qrcode(self, auth, token: str) -> dict:
        """轮询二维码状态。status: new / scanned / confirmed / expired。

        实录里这个是 **POST**，token 在表单 body 里，不在 query。
        """
        data = {
            "need_logo": "false",
            "is_frontier": "true",
            "token": token,
            "is_new_login": "1",
            "next": HOME_URL,
            "need_short_url": "true",
        }
        # data 要先于 params 构造：sign 把 query 和 body 一起签
        # device_fp=True：这个接口带 p_ca / p_ca_real / fp / verifyFp（3.4.4 真值）
        # Chrome 151's actual jingxuan QR request carries the full 30-field
        # query.  In particular, both msToken and a_bogus are present after
        # sign/qs; omitting either changes the browser risk input and makes
        # the request shape diverge even when the body is otherwise correct.
        params = self._sdk_params(auth, {"is_from_iesaccountsaas": "1"},
                                  data=data, device_fp=True,
                                  with_ms_token=True)
        params.with_a_bogus(data, host="login.douyin.com")
        resp = auth.request("POST", self.base_url + "check_qrconnect/",
                             headers=headers_with_cookie(
                                 self._passport_headers(
                                     auth, form=True,
                                     api="/passport/web/check_qrconnect/").get(),
                                 scoped_cookies(auth, "qr")),
                                 params=params.get(), data=data,
                                 verify=False, timeout=20)
        set_cookies = resp.cookies.get_dict()
        merge_set_cookies(auth, set_cookies)
        apply_ticket_guard(auth, resp.headers, set_cookies)
        DYLoginApi._harvest_sec_ts(auth, resp.headers)
        # The QR poll endpoint occasionally returns an empty HTTP 200 body
        # during edge retries.  Treat that as a transient poll failure instead
        # of letting ``resp.json()`` abort the whole login flow; the caller's
        # existing error_code=7 backoff then retries with the same QR token.
        raw = (resp.text or '').strip()
        if not raw:
            logger.warning(
                'check_qrconnect 返回空响应，暂按临时限频重试 '
                '(HTTP %s, logid=%s)',
                resp.status_code, resp.headers.get('X-Tt-Logid', ''),
            )
            return {
                'data': {
                    'error_code': 7,
                    'description': 'empty response from QR poll edge',
                },
                'message': 'retry',
            }
        if not raw.startswith('{'):
            raise RuntimeError(
                'check_qrconnect 返回非 JSON（可能命中登录风控页）：'
                f'HTTP {resp.status_code}，前 120 字：{raw[:120]!r}，'
                f'logid={resp.headers.get("X-Tt-Logid", "")}'
            )
        res = resp.json()
        if (_passport_profile("DY_PASSPORT_COOKIE_PROFILE")
                in ("chrome_current", "chrome_current_early")
                and (res.get("data") or {}).get("status") == "expired"):
            auth._qr_refresh_ready = True
            # Chrome writes this page cookie on the first expired-code
            # transition.  It is deterministic for the local day and can be
            # frozen for fixture replay; unlike the other opaque cookies it
            # is safe to derive without reading Chrome's cookie store.
            auth.cookie.setdefault("download_guide", self._download_guide())
            # The page SDK also rewrites passport_auth_mix_state at this
            # expiry boundary (48 chars on the initial phone form, 32 chars
            # on the refreshed QR/login jar in reqid=733/735).  Preserve a
            # caller-supplied captured value, otherwise match the observed
            # post-expiry length rather than leaking the initial state.
            mix_state = auth.cookie.get("passport_auth_mix_state")
            if mix_state and len(mix_state) != 32:
                # Chrome generates a fresh random state at the expiry
                # boundary.  The length is observable, but the exact bytes
                # are not derivable without the browser's Math.random trace;
                # never retain the old captured provenance after replacing it.
                auth.cookie["passport_auth_mix_state"] = generate_passport_auth_mix_state(32)
                marker = getattr(auth, "mark_cookie_source", None)
                if marker:
                    marker(
                        "passport_auth_mix_state", "unproven_synthetic",
                        detail="QR expiry refresh uses local random bytes; browser trace absent",
                    )
            auth.cookie_str = "; ".join(
                f"{k}={v}" for k, v in auth.cookie.items())
        # error_code=7「访问太频繁」是轮询限频，属于可重试的瞬时状态，
        # 不能当成致命错误——浏览器遇到它也只是退避后接着轮询
        if ((res.get("data") or {}).get("error_code")) != 7:
            self._raise_if_blocked("check_qrconnect/", res)
        return res

    @staticmethod
    def _download_guide(stage="1") -> str:
        """Build Chrome's ``download_guide`` Cookie value for a page stage."""
        fixed = os.getenv("DY_PASSPORT_DOWNLOAD_GUIDE")
        if fixed:
            return fixed
        fixed_date = (os.getenv("DY_PASSPORT_FIXED_DATE")
                      or os.getenv("DY_FIXED_DATE"))
        if fixed_date:
            date_text = fixed_date.replace("-", "")
        else:
            date_text = datetime.datetime.now().strftime("%Y%m%d")
        # The wire value is a URL-encoded JSON string, including quotes.
        return urllib.parse.quote(json.dumps(f"{stage}/{date_text}/0"), safe="")

    def qrcode_login(self, timeout=300, show_qr=True, poll_interval=None,
                     on_qrcode=None, proxies=None):
        """完整扫码登录，返回登录后的 auth。

        二维码实测只有约 60 秒有效期，所以过期后自动换一张继续等，
        直到整体 `timeout` 用完。

        :param on_qrcode: 可选回调，每换一张码调用一次，入参是 qrcode_index_url。
        """
        poll_interval = self.POLL_INTERVAL if poll_interval is None else poll_interval
        page_started_at = time.time()
        # Keep the no-proxy call signature compatible with lightweight test
        # doubles and older integrations that replace ``bootstrap_auth`` with
        # a zero-argument callable.  Pass the keyword only when a proxy was
        # actually requested.
        auth = (self.bootstrap_auth() if proxies is None
                else self.bootstrap_auth(proxies=proxies))
        auth._ms_pinned = True
        deadline = time.time() + timeout
        token = None
        token_born = 0.0
        wait = poll_interval
        throttled_since = None
        scanned = False
        # Chrome first sends one full /web/common report shortly after the
        # initial successful status read.  An independent page timer then
        # sends a compact msgType=2 behavior report at page_start+300s,
        # +600s, ... .  check_qrconnect's own x-ms-token response headers are
        # ignored; only these common reports rotate the query token.
        first_status_at = None
        bootstrap_common_done = False
        next_behavior_common_at = page_started_at + self.MS_COMMON_INTERVAL
        # 本轮是否成功读到了二维码状态。限频时为 False，此时不允许换码。
        fresh_read = False

        while time.time() < deadline:
            # Run the one-shot bootstrap common report at the same boundary as
            # Chrome: after the first successful check has had one poll
            # interval to settle, and before the next check is sent.  Do not
            # fire during an error_code=7 window or once the QR is expired.
            now = time.time()
            if (token is not None and first_status_at is not None
                    and not bootstrap_common_done
                    and now - first_status_at >= self.POLL_INTERVAL):
                try:
                    refreshed = auth.refresh_mstoken(common=True)
                    bootstrap_common_done = True
                    logger.info("bootstrap common msToken refreshed (%d)"
                                % len(refreshed or ""))
                except Exception as err:
                    bootstrap_common_done = True
                    logger.warning("bootstrap common msToken refresh failed: %s", err)
            elif (token is not None and bootstrap_common_done
                  and now >= next_behavior_common_at):
                try:
                    refreshed = auth.refresh_mstoken(
                        common=True, common_behavior=True)
                    logger.info("behavior common msToken refreshed (%d)"
                                % len(refreshed or ""))
                except Exception as err:
                    logger.warning("behavior common msToken refresh failed: %s", err)
                finally:
                    # Keep the timer anchored to page start even if a poll or
                    # a network retry delayed this iteration.
                    while next_behavior_common_at <= now:
                        next_behavior_common_at += self.MS_COMMON_INTERVAL
            # 二维码只活 60 秒左右，到期要换一张。但换码有个硬前提：
            # **必须先成功读到状态**。
            #
            # 2026-08-17 实测踩过：被限频（error_code=7）期间状态读不到，代码仍按
            # 55 秒兜底换了码，而用户正好扫的是那张 —— 扫码直接作废，界面上表现为
            # 「我扫过了它还一直弹新码」。限频时我们对这张码是 new 还是 scanned
            # 一无所知，此时换码是纯粹的有害操作。
            #
            # 所以换码条件收紧成：本轮成功读到了状态（`fresh_read`）、且读到的是
            # 还没人扫的 `new`、且已超过 TTL。读到 `scanned` 永不换（用户正停在
            # 手机确认页上），读到 `expired` 立刻换（见下面的分支）。
            pending = None      # 换码检查已经拿到的状态，复用它，别重复请求
            if (token is not None and fresh_read and not scanned
                    and time.time() - token_born > self.QR_TTL):
                # 换码前再查一次。轮询与这里之间有约一个 poll_interval 的空窗，
                # 用户正好在那几秒扫的话，按时间直接换掉同样会把这次扫码作废
                # （和限频那次是同一类错误，只是窗口小得多）。
                last = (self.check_qrcode(auth, token).get("data") or {})
                if last.get("status") == "confirmed":
                    self._follow_login_redirect(auth, last.get("redirect_url"))
                    auth._ms_pinned = False
                    logger.info("扫码登录成功")
                    return auth
                if last.get("status") == "scanned":
                    scanned = True
                    logger.info("换码前发现已扫码，这张保留，请在手机上确认")
                    # ⚠️ 这里必须把结果带下去。以前是查完就丢，下面 888 行紧接着
                    # 又查一遍 —— 同一秒发两个 check_qrconnect，而浏览器是稳定
                    # 5.14 秒一发，从不并发。2026-08-22 的日志里
                    # 「轮询 72 / 73 同为 16:59:04」就是这个，紧跟着就开始返
                    # error_code=7。把这一发的结果复用掉，节奏才和浏览器一致。
                    pending = last
                else:
                    logger.info("二维码到期，换一张")
                    token, fresh_read = None, False

            if token is None:
                data = (self.get_qrcode(auth).get("data") or {})
                token, qr_url = data.get("token"), data.get("qrcode_index_url")
                if not token:
                    raise RuntimeError(f"获取二维码失败: {data}")
                token_born = time.time()
                logger.info(
                    f"请用抖音 App 扫码登录（二维码链接长度={len(qr_url or '')}）"
                )
                if show_qr:
                    self.print_qrcode(qr_url)
                if on_qrcode:
                    on_qrcode(qr_url)

            if pending is not None:
                info = pending
            else:
                info = self.check_qrcode(auth, token).get("data") or {}
            if info.get("error_code") == 7:      # 限频，退避后接着轮询
                fresh_read = False               # 状态未知，这期间绝不换码
                throttled_since = throttled_since or time.time()
                stuck = time.time() - throttled_since
                if stuck > self.THROTTLE_GIVEUP:
                    raise RuntimeError(
                        f"check_qrconnect 连续 {int(stuck)} 秒返回 error_code=7"
                        "（访问太频繁）。这期间扫码状态完全读不到，就算扫了也识别不了，"
                        "继续轮询只会把限频拖得更久。请等几分钟再重试，"
                        "并避免短时间内反复重启登录。")
                wait = min(wait * 2, 60)
                time.sleep(wait)
                continue
            throttled_since = None
            wait = poll_interval

            status = info.get("status")
            fresh_read = bool(status)
            if fresh_read and first_status_at is None:
                first_status_at = time.time()
            if status == "confirmed":
                self._follow_login_redirect(auth, info.get("redirect_url"))
                auth._ms_pinned = False
                logger.info("扫码登录成功")
                return auth
            if status == "expired":
                logger.info("二维码已过期，换一张继续等")
                token, scanned, fresh_read = None, False, False
                if not bootstrap_common_done:
                    first_status_at = None
                continue
            if status == "scanned":
                scanned = True
                logger.info("已扫码，请在手机上确认（该码不再轮换，安心确认）")
            time.sleep(wait)
        auth._ms_pinned = False
        raise TimeoutError("扫码登录超时")

    # ---------- 短信验证码登录 ----------
    @staticmethod
    def _format_sms_phone(phone: str) -> str:
        """Format the phone exactly as the Chrome passport form does.

        The live request decrypted to ``+86 #############`` (a literal space
        after the country code), not to a bare 11-digit string.  Accept the
        common caller spellings but always emit that browser representation;
        reject other formats instead of silently producing a different
        encrypted value.
        """
        raw = str(phone or "").strip()
        if re.fullmatch(r"\d{11}", raw):
            return "+86 " + raw
        if re.fullmatch(r"\+86\d{11}", raw):
            return "+86 " + raw[3:]
        if re.fullmatch(r"\+86\s\d{11}", raw):
            return "+86 " + raw[4:]
        raise ValueError(
            "phone must be an 11-digit mainland number or '+86 <11 digits>'"
        )

    @staticmethod
    def _format_sms_code(code: str) -> str:
        """Validate the six-digit code shape used by ``is6Digits=1``."""
        raw = str(code or "").strip()
        if not re.fullmatch(r"\d{6}", raw):
            raise ValueError("code must be exactly six decimal digits")
        return raw

    @staticmethod
    def _ensure_sms_ms_token(auth) -> str:
        """Ensure the SMS page has Chrome's post-common msToken.

        `/web/r/token` returns the initial ~164-byte token.  Chrome sends a
        full `/web/common` report before `send_code`; both SMS requests then
        carry the rotated ~172-byte token.  Do not silently fall back to a
        shorter generated value because that changes the signed request.
        """
        def token_len(value):
            return len(urllib.parse.unquote(str(value or "")))

        cached = getattr(auth, "_ms_cache", "") or ""
        if token_len(cached) >= 170:
            return cached
        seeded = auth.msToken
        if token_len(seeded) >= 170:
            return seeded
        rotated = auth.refresh_mstoken(common=True, sms=True)
        if token_len(rotated) < 170:
            raise RuntimeError(
                "短信请求要求 /web/common 轮换后的 msToken（解码后至少 170 字节）；"
                f"当前只有 {token_len(rotated)} 字节，已拒绝发送不对齐请求"
            )
        return rotated

    @staticmethod
    def _assert_sms_cookie_shape(auth, order=None, *, expected_length=None):
        """Fail closed when strict SMS mode lacks a browser cookie vector.

        The names alone are not enough: Chrome 151 has two observed SMS page
        lifecycles.  The fresh reqid=558 request has 23 pairs/3,280 bytes and
        a 48-character ``passport_auth_mix_state``; the older delayed-submit
        fixture has 26 pairs/3,749 bytes and a 32-character state.  Select the
        expected vector from the same profile used by ``scoped_cookies`` so a
        current request is never padded with historical fields.
        """
        if not getattr(auth, "strict_browser_alignment", False):
            return
        profile = _sms_cookie_profile(auth)
        if profile == "historical_26":
            selected_order = order or SMS_COOKIE_ORDER
            expected_total = 3749 if expected_length is None else expected_length
            expected = {
                "enter_pc_once": 1, "UIFID_TEMP": 224, "is_support_rtm_web_ts": 1,
                "hevc_supported": 4, "home_can_add_dy_2_desktop": 7,
                "odin_tt": 160, "strategyABtestKey": 20, "is_dash_user": 1,
                "passport_csrf_token": 32, "passport_csrf_token_default": 32,
                "__security_mc_1_s_sdk_crypt_sdk": 18,
                "bd_ticket_guard_regenerate_keys_time": 19,
                "bd_ticket_guard_client_web_domain": 1,
                "download_guide": 22, "MONITOR_WEB_ID": 36, "UIFID": 384,
                "IsDouyinActive": 4, "stream_recommend_feed_params": 324,
                "ttwid": 127, "biz_trace_id": 8,
                "bd_ticket_guard_client_data": 304,
                "bd_ticket_guard_client_data_v2": 354,
                "sdk_source_info": 472, "bit_env": 512,
                "gulu_source_res": 100, "passport_auth_mix_state": 32,
            }
        else:
            selected_order = SMS_CURRENT_COOKIE_ORDER
            expected_total = (SMS_CURRENT_COOKIE_LENGTH
                              if expected_length is None else expected_length)
            expected = {
                # The current 23-cookie lifecycle has two additional
                # server-issued value shapes in the wild.  A compact 160-byte
                # UIFID_TEMP + 96-byte odin_tt pair is what older, still-valid
                # anonymous jars (including the project's .env capture) use;
                # the newer page emits 224 + 160.  Both must be accepted when
                # the values are actually captured rather than synthesized.
                "enter_pc_once": 1, "UIFID_TEMP": {160, 224},
                "odin_tt": {96, 128, 160},
                "is_support_rtm_web_ts": 1, "hevc_supported": 4,
                "IsDouyinActive": 4, "home_can_add_dy_2_desktop": 7,
                "stream_recommend_feed_params": {323, 324},
                "strategyABtestKey": 20, "is_dash_user": 1,
                "passport_csrf_token": 32, "passport_csrf_token_default": 32,
                "ttwid": 127, "biz_trace_id": 8,
                "__security_mc_1_s_sdk_crypt_sdk": 18,
                "bd_ticket_guard_regenerate_keys_time": 19,
                "bd_ticket_guard_client_data": 304,
                "bd_ticket_guard_client_web_domain": 1,
                "bd_ticket_guard_client_data_v2": {354, 552},
                "sdk_source_info": 472, "bit_env": 512,
                "gulu_source_res": 100, "passport_auth_mix_state": {32, 48},
            }
        jar = auth.cookie or {}
        missing = [name for name in selected_order if jar.get(name) in (None, "")]
        if missing:
            raise RuntimeError(
                "严格短信登录缺少 Chrome Cookie: " + ", ".join(missing)
            )
        wrong = [
            f"{name}={len(str(jar.get(name)))} (expected {size})"
            for name, size in expected.items()
            if len(str(jar.get(name) or "")) not in (
                set(size) if isinstance(size, (set, frozenset)) else {size}
            )
        ]
        if wrong:
            raise RuntimeError(
                "严格短信登录 Cookie 长度与 Chrome 实录不一致: "
                + ", ".join(wrong)
            )
        serialized_cookies = _cookie_view(auth, selected_order)
        actual_names = list(serialized_cookies)
        if actual_names != list(selected_order):
            raise RuntimeError(
                "严格短信登录 Cookie 名称/顺序与 Chrome 实录不一致: "
                f"实际={actual_names!r}，期望={list(selected_order)!r}"
            )
        serialized = cookie_header(serialized_cookies)
        if profile == "current_23":
            # Derive the allowed header lengths from the observed baseline
            # vector instead of hard-coding only the newest 224/160 pair.
            # Cookie names, separators, and ordering are fixed; value-length
            # deltas therefore map linearly to the captured 3,280-byte total.
            base_lengths = {
                "UIFID_TEMP": 224, "odin_tt": 160,
                "stream_recommend_feed_params": 323,
                "bd_ticket_guard_client_data_v2": 354,
                "passport_auth_mix_state": 48,
            }
            import itertools
            variants = [
                expected[name] if isinstance(expected[name], (set, frozenset))
                else {expected[name]}
                for name in base_lengths
            ]
            allowed_totals = {
                expected_total + sum(value - base_lengths[name]
                                     for name, value in zip(base_lengths, combo))
                for combo in itertools.product(*variants)
            }
        else:
            allowed_totals = {expected_total}
        if len(serialized) not in allowed_totals:
            raise RuntimeError(
                "严格短信登录 Cookie Header 长度与 Chrome 实录不一致: "
                f"{len(serialized)}，期望 {sorted(allowed_totals)}"
            )

    @staticmethod
    def _maybe_refresh_sms_page_cookies(auth, *, strict: bool = False) -> None:
        """Apply the browser's post-expiry SMS-page cookie transition.

        In the live page, send_code carries ``download_guide=1/<date>/0``.
        After the first ~55-second challenge window Chrome rewrites only that
        value to ``2/<date>/0`` and serializes it at the end of the Cookie
        header.  The 2026-08-29 same-session capture (reqid=1765 -> 1874)
        showed that every other cookie name, value, and length stayed
        byte-for-byte unchanged.  Do not rotate or synthesize any opaque SDK
        cookie here: doing so changes the browser request and invalidates the
        session.  The transition is deliberately deferred until the final
        sms_login call and only runs when our same-session send timestamp proves
        that the boundary was crossed.
        """
        if getattr(auth, "_sms_sent_at", None) is None:
            return
        # The fresh 23-cookie Chrome 151 lifecycle has no download_guide at
        # all.  Its post-submit transition is still unobserved, so do not
        # synthesize the historical marker merely because the caller waited
        # longer than the old challenge TTL.
        if _sms_cookie_profile(auth) != "historical_26":
            return
        if (time.time() - auth._sms_sent_at) < DYLoginApi.QR_TTL:
            return
        current = urllib.parse.unquote(
            str((auth.cookie or {}).get("download_guide") or ""))
        if current.startswith("2/"):
            return
        # Reinsert the existing key so the underlying mapping also reflects
        # Chromium's write order.  ``scoped_cookies(..., "sms_login")`` uses
        # the explicit refresh order below, but preserving dict order matters
        # for callers that inspect or persist the session after this request.
        value = DYLoginApi._download_guide("2")
        auth.cookie.pop("download_guide", None)
        auth.cookie["download_guide"] = value
        auth.cookie_str = "; ".join(
            f"{k}={v}" for k, v in auth.cookie.items())

    @staticmethod
    def _phone_sso_post(auth, url, data):
        """POST one current-page SSO request and absorb anti-bot HTML once."""
        for attempt in range(2):
            params = DYLoginApi._phone_sso_params(auth)
            resp = auth.request(
                "POST", url,
                headers=DYLoginApi._phone_sso_headers(auth),
                params=params.get(),
                data=urllib.parse.urlencode(data),
                verify=False, timeout=20,
                proxies=getattr(auth, "_proxies", None),
            )
            set_cookies = resp.cookies.get_dict()
            merge_set_cookies(auth, set_cookies)
            apply_ticket_guard(auth, resp.headers, set_cookies)
            text = resp.text or ""
            if text.lstrip().startswith("{"):
                try:
                    return resp, resp.json()
                except Exception:
                    pass
            if attempt == 0 and DYLoginApi._solve_gfkadpd(auth, resp):
                continue
            raise RuntimeError(
                "手机号 SSO 接口返回的不是 JSON（多为 gfkadpd 拦截页或页面版本切换）；"
                f"HTTP {resp.status_code}，前 120 字：{text[:120]!r}"
            )
        raise RuntimeError("手机号 SSO 请求未完成")

    def _send_sms_code_sso(self, auth, phone: str) -> dict:
        """Current login.douyin.com page: /send_activation_code/v2/."""
        if getattr(auth, "phone_login_profile", "sso") != "sso":
            auth.phone_login_profile = "sso"
        data = {
            "mix_mode": "1",
            "mobile": passport_encrypt(self._format_sms_phone(phone)),
            "type": "3731",
            "is6Digits": "1",
            "fixed_mix_mode": "1",
        }
        _, res = self._phone_sso_post(auth, PHONE_SSO_SEND_API, data)
        mobile_ticket = (res.get("data") or {}).get("mobile_ticket")
        if mobile_ticket:
            auth.mobile_ticket = mobile_ticket
        auth._sms_sent_at = time.time()
        if res.get("error_code") not in (0, None):
            logger.warning(f"发送验证码需要过验证或失败: {res.get('description') or res}")
        return res

    def _phone_login_sso(self, auth, phone: str, code: str):
        """Current login.douyin.com page: /quick_login/v2/."""
        if getattr(auth, "_sms_sent_at", None) is None:
            raise RuntimeError(
                "quick_login 必须复用同一 auth 的 send_sms_code 会话；"
                "请先调用 send_sms_code(auth, phone)"
            )
        data = {
            "mix_mode": "1",
            "mobile": passport_encrypt(self._format_sms_phone(phone)),
            "code": passport_encrypt(self._format_sms_code(code)),
            "service": "https://www.toutiao.com",
            "fixed_mix_mode": "1",
        }
        resp, res = self._phone_sso_post(auth, PHONE_SSO_LOGIN_API, data)
        redirect = ((res.get("data") or {}).get("redirect_url")
                    or res.get("redirect_url"))
        if redirect:
            self._follow_login_redirect(auth, redirect)
        if not auth.ticket:
            logger.warning("quick_login 响应未下发 ticket，需检查 ticket-guard 后续链路")
        return res, auth

    def send_sms_code(self, auth, phone: str) -> dict:
        """发送短信验证码，严格复现 Chrome 151 的表单字节序。

        默认 ``DY_PHONE_LOGIN_PROFILE=passport_web``，即
        ``www.douyin.com/jingxuan`` 嵌入弹窗的 2026-08-29 Network 实录，
        走 ``/passport/web/send_code/``，body 顺序是
        ``is6Digits, mix_mode, mobile, type, fixed_mix_mode``。显式设置
        ``DY_PHONE_LOGIN_PROFILE=sso`` 才走裸 ``login.douyin.com`` 页的
        ``/send_activation_code/v2/`` 备用链：

        ``is6Digits=1&mix_mode=1&mobile=<XOR5+hex>&type=3731&fixed_mix_mode=1``

        这五个字段都存在，且顺序固定；仅发送 ``mobile`` 是旧实现的错误，
        在重复请求时会改变风控输入。``type=3731`` 是浏览器发出的已加密
        表单值（解码后为明文 ``24``），不能按直觉改成别的类型。
        """
        if (getattr(auth, "phone_login_profile", None)
                or _phone_login_profile()) == "sso":
            return self._send_sms_code_sso(auth, phone)
        # Ensure the page-derived shared-domain cookies are present before the
        # first SMS request.  Strict mode selects the observed current_23 or
        # historical_26 vector and rejects any missing/incorrect value instead
        # of sending a shorter or padded request.
        self._assert_sms_cookie_shape(auth, SMS_COOKIE_ORDER)
        self._ensure_sms_ms_token(auth)
        mobile = passport_encrypt(self._format_sms_phone(phone))
        data = {
            "is6Digits": "1",
            "mix_mode": "1",
            "mobile": mobile,
            "type": "3731",
            "fixed_mix_mode": "1",
        }
        # Chrome 151's actual passport-web SMS request has the full 30-field
        # query.  Both msToken and a_bogus are present and are part of the
        # browser risk input; omitting either changes the request shape.
        params = self._sdk_params(auth, {"is_from_iesaccountsaas": "1"},
                                  data=data, device_fp=True,
                                  with_ms_token=True)
        params.with_a_bogus(data, host="login.douyin.com")
        body = urllib.parse.urlencode(data)
        resp = auth.request(
            "POST", self.base_url + "send_code/",
            headers=headers_with_cookie(
                self._passport_headers(
                    auth, form=True, api="/passport/web/send_code/",
                    strict_dtrait=True, body_length=len(body.encode()),
                    wire_accept_encoding=True).get(),
                scoped_cookies(auth, "sms")),
            params=params.get(),
            # Pass the already ordered form bytes.  Relying on a client-side
            # mapping encoder makes field ordering an implementation detail;
            # Chrome's body is exactly 87 bytes.  Split Cookie fields to match
            # Chromium's HTTP/2 cookie crumbling on the wire.
            data=body, split_cookie_header=True,
            verify=False, timeout=20,
            proxies=getattr(auth, "_proxies", None),
        )
        merge_set_cookies(auth, resp.cookies.get_dict())
        res = resp.json()
        # The successful send response carries a one-shot mobile_ticket.  Keep
        # it as non-persistent session state for diagnostics.  The live
        # sms_login body was captured separately and contains no
        # mobile_ticket field, so it is intentionally not sent by phone_login.
        mobile_ticket = (res.get("data") or {}).get("mobile_ticket")
        if mobile_ticket:
            auth.mobile_ticket = mobile_ticket
        auth._sms_sent_at = time.time()
        if res.get("error_code") not in (0, None):
            logger.warning(f"发送验证码需要过验证或失败: {res.get('description') or res}")
        return res

    def phone_login(self, auth, phone: str, code: str):
        """用手机号 + 六位验证码登录（严格按选定页面表单顺序）。

        默认走 ``www.douyin.com/jingxuan`` 嵌入弹窗的
        ``/passport/web/sms_login/``，body 顺序为
        ``service, mix_mode, mobile, code, fixed_mix_mode``；裸
        ``login.douyin.com`` 的 ``/quick_login/v2/`` 必须显式设置
        ``DY_PHONE_LOGIN_PROFILE=sso``。
        响应中的 session Cookie 与 ticket-guard server-data 会合并回 auth。
        """
        if (getattr(auth, "phone_login_profile", None)
                or _phone_login_profile()) == "sso":
            return self._phone_login_sso(auth, phone, code)
        if getattr(auth, "_sms_sent_at", None) is None:
            raise RuntimeError(
                "sms_login 必须复用同一 auth 的 send_sms_code 会话；"
                "请先调用 send_sms_code(auth, phone)"
            )
        self._maybe_refresh_sms_page_cookies(
            auth, strict=bool(getattr(auth, "strict_browser_alignment", False))
        )
        self._assert_sms_cookie_shape(auth, SMS_LOGIN_REFRESH_COOKIE_ORDER)
        self._ensure_sms_ms_token(auth)
        data = {
            "service": HOME_URL,
            "mix_mode": "1",
            "mobile": passport_encrypt(self._format_sms_phone(phone)),
            "code": passport_encrypt(self._format_sms_code(code)),
            "fixed_mix_mode": "1",
        }
        # Chrome 151's actual passport-web SMS request has the same full
        # 30-field query as send_code, including msToken and a_bogus.
        params = self._sdk_params(auth, {"is_from_iesaccountsaas": "1"},
                                  data=data, device_fp=True,
                                  with_ms_token=True)
        params.with_a_bogus(data, host="login.douyin.com")
        body = urllib.parse.urlencode(data)
        resp = auth.request(
            "POST", self.base_url + "sms_login/",
            headers=headers_with_cookie(
                self._passport_headers(
                    auth, form=True, api="/passport/web/sms_login/",
                    strict_dtrait=True, body_length=len(body.encode()),
                    wire_accept_encoding=True).get(),
                scoped_cookies(auth, "sms_login")),
            params=params.get(),
            data=body, split_cookie_header=True,
            verify=False, timeout=20,
            proxies=getattr(auth, "_proxies", None),
        )
        set_cookies = resp.cookies.get_dict()
        merge_set_cookies(auth, set_cookies)
        got_ticket = apply_ticket_guard(auth, resp.headers, set_cookies)
        # sms_login exposes bd-ticket-guard-sec-ts on the response.  Harvest
        # it after applying server-data so the regenerated client_data_v2 is
        # bound to this login's ts_sign, matching the browser's post-login
        # ticket-guard refresh.
        DYLoginApi._harvest_sec_ts(auth, resp.headers)
        res = resp.json()
        redirect = (res.get("data") or {}).get("redirect_url") or res.get("redirect_url")
        if redirect:
            self._follow_login_redirect(auth, redirect)
        if not got_ticket and not auth.ticket:
            logger.warning("登录响应未下发 ticket，bd-ticket-guard 接口可能不可用")
        return res, auth

    # ---------- 收尾 ----------
    def _follow_login_redirect(self, auth, redirect_url, max_hops=5):
        """跟随登录重定向，把各跳的 Set-Cookie 都收进来。"""
        if not redirect_url:
            return
        headers = HeaderBuilder().build(HeaderType.DOC)
        url = redirect_url
        for _ in range(max_hops):
            resp = auth.request("GET", url,
                                headers=headers_with_cookie(headers.get(), scoped_cookies(auth)),
                                verify=False, timeout=20, allow_redirects=False)
            set_cookies = resp.cookies.get_dict()
            merge_set_cookies(auth, set_cookies)
            apply_ticket_guard(auth, resp.headers, set_cookies)
            if resp.status_code not in (301, 302, 303, 307, 308):
                break
            url = resp.headers.get("Location")
            if not url:
                break
        auth.cookie.pop("msToken", None)
        auth.cookie_str = "; ".join(f"{k}={v}" for k, v in auth.cookie.items())
        auth._ttwid = auth.cookie.get("ttwid", "")

    @staticmethod
    def print_qrcode(url: str):
        """在终端里画二维码，无需打开图片查看器。"""
        try:
            import qrcode
            qr = qrcode.QRCode(border=1)
            qr.add_data(url)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
        except Exception as err:
            logger.warning(f"终端二维码渲染失败（可直接打开上面的链接）: {err}")

    def save_credential(self, auth) -> str:
        """把登录凭证写入 .env。"""
        from dotenv import set_key
        values = {
            "DY_COOKIES": "; ".join(f"{k}={v}" for k, v in auth.cookie.items()),
            "DY_TICKET": auth.ticket or "",
            "DY_TS_SIGN": auth.ts_sign or "",
            "DY_CLIENT_CERT": auth.client_cert or "",
            "DY_PRIVATE_KEY": auth.private_key or "",
            # 设备绑定的，跟着一起落盘，免得下次 bootstrap 时丢了
            "DY_DTRAIT_BLOB": auth.dtrait_blob or "",
        }
        for key, value in values.items():
            if value:
                set_key(ENV_FILE, key, value)
        return os.path.abspath(ENV_FILE)

    def get_login_auth(self, timeout=180):
        """优先读 .env 里的凭证，没有就扫码登录并写回。"""
        from utils.common_util import load_env
        auth = load_env()
        if auth.ticket and auth.private_key and auth.cookie.get("sessionid"):
            return auth
        auth = self.qrcode_login(timeout=timeout, proxies=getattr(auth, "_proxies", None))
        logger.info(f"登录凭证已写入 {self.save_credential(auth)}")
        return auth
