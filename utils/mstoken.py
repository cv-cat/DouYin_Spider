# -*- coding: utf-8 -*-
"""msToken"""

import copy
import json
import os
import random
import re
import time
import urllib.parse
import uuid

from utils import http_client as requests
requests.packages.urllib3.disable_warnings()

from utils.strdata_pure import build_report_body, encode_strdata

from utils.fingerprint import get_profile

# Chrome's login lifecycle uses both endpoints:
# - /web/r/token seeds the initial 164-byte token;
# - /web/common sends one full msgType=1 report, then a 783-byte msgType=2
#   behavior heartbeat every 300 seconds.  Each common response rotates the
#   query token to a fresh 172-byte value.
_TOKEN_URL = "https://mssdk.bytedance.com/web/r/token?ms_appid=6383"
# creator.douyin.com 页面用自己的 appid 轮换（2026-10-17 页面5 实测：
# POST mssdk/web/r/token?ms_appid=2906 → x-ms-token 184 字符，比 6383 的 164 长）
_CREATOR_TOKEN_URL = "https://mssdk.bytedance.com/web/r/token?ms_appid=2906"
_COMMON_URL = "https://mssdk.bytedance.com/web/common"

_cache = {"token": "", "ts": 0}
_creator_cache = {"token": "", "ts": 0}
_TTL = 600

_COMMON_PROFILE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "mstoken_common_profile.json")
_common_profile_cache = None


def _mssdk_headers(storage_access=False):
    """Return the controlled headers Chrome sends to mssdk.

    ``curl_cffi`` is intentionally called with ``default_headers=False`` in
    this project, so the browser network-layer headers must be supplied here
    explicitly.  The live Chrome 151 capture shows these on both
    ``/web/r/token`` and ``/web/common``: the JS-set ``sec-ch-ua*`` trio plus
    ``cache-control``/``pragma`` that Chrome adds to the wire request.
    ``accept-encoding`` and ``content-length`` remain transport-generated.
    """
    prof = get_profile()
    headers = {
        # JS insertion order from the live request.
        "sec-ch-ua-platform": prof["sec_ch_ua_platform"],
        "referer": "https://www.douyin.com/",
        "user-agent": prof["ua"],
        "sec-ch-ua": prof["sec_ch_ua"],
        "content-type": "text/plain;charset=UTF-8",
        "sec-ch-ua-mobile": "?0",
        # Chrome network-layer additions (curl_cffi does not add them when
        # default_headers=False).
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "origin": "https://www.douyin.com",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
    }
    if storage_access:
        headers["sec-fetch-storage-access"] = "active"
    return headers


def _load_common_profile():
    """Load the full `/web/common` fingerprint captured from Chrome.

    `/web/r/token` and `/web/common` deliberately use different payload
    shapes.  The former is the compact nWID/wID report in
    :func:`build_report_body`; the latter contains battery/document/window,
    the complete nWID probe and a wID with ``msgType=1``.  Keeping this as a
    separate template prevents accidentally sending the short report to the
    post-scan endpoint.
    """
    global _common_profile_cache
    if _common_profile_cache is None:
        with open(_COMMON_PROFILE_PATH, encoding="utf-8") as f:
            _common_profile_cache = json.load(f)
    return _common_profile_cache


def build_common_report_body(aid=6383, page_id=6241, fixed_uuid=None,
                             fixed_collect_time=None, fixed_timestamp=None,
                             fixed_tsp=None, fixed_nonce=None, sms=False):
    """Build the full Chrome `/web/common` strData envelope.

    The captured plaintext is stable except for the per-report UUID,
    collection time and the wID timestamp.  Preserve key insertion order and
    the browser's compact JSON separators so the encrypted body remains
    13,755 bytes for the fixed Chrome vector used by the login capture.
    """
    profile = copy.deepcopy(_load_common_profile())
    if fixed_timestamp is None:
        fixed_timestamp = os.getenv("DY_MSTOKEN_FIXED_TIMESTAMP")
    now_ms = int(time.time() * 1000) if fixed_timestamp is None else int(fixed_timestamp)
    # The SMS page's full msgType=1 report is a separate SDK phase from the
    # QR/common profile.  Only apply the SMS-specific values when explicitly
    # requested; QR regression vectors use the captured profile as-is.
    ub_override = os.getenv("DY_MSTOKEN_UB_CODE")
    ub_code = int(ub_override) if ub_override is not None else None
    if sms or ub_code is not None:
        ub_code = 12 if ub_code is None else ub_code
        profile["ubCode"] = ub_code
    # msgType=1 has its own fingerprint snapshot.  It is not the same nWID as
    # /web/r/token (notably canvas/audio), so preserve the captured common
    # profile and only overlay device fields that are shared across all
    # request surfaces.  The current Chrome 151 common report has a running
    # AudioContext and canvas CRC ``A7996F6A``; those values are also used by
    # the QR/common lifecycle, not only by the SMS form.
    n = copy.deepcopy(profile.get("nWID") or {})
    if ub_code is not None:
        n["ubCode"] = ub_code
    canvas = n.get("canvas") or {}
    canvas["crc32"] = os.getenv("DY_MSTOKEN_CANVAS_CRC32", "A7996F6A")
    n["canvas"] = canvas
    audio = n.get("audio") or {}
    audio_context = audio.get("audioContext") or {}
    audio_context["state"] = "running"
    audio["audioContext"] = audio_context
    n["audio"] = audio
    # nWID.custom is itself a JSON string in the browser payload.
    raw_custom = n.get("custom")
    if isinstance(raw_custom, str):
        try:
            custom = json.loads(raw_custom)
        except Exception:
            custom = {}
    else:
        custom = dict(raw_custom or {})
    custom.setdefault("version", n.get("ms_version", "0.0.0.1"))
    custom.setdefault("fxgDid", "")
    if fixed_uuid is None:
        fixed_uuid = os.getenv("DY_MSTOKEN_FIXED_UUID") or str(uuid.uuid4())
    custom["uuid"] = fixed_uuid
    if fixed_collect_time is None:
        fixed_collect_time = os.getenv("DY_MSTOKEN_FIXED_COLLECT_TIME")
    if fixed_collect_time is None:
        # Captured Chrome performance.now() value for the SMS page's first
        # full common report. QR/common retains its existing dynamic sample.
        fixed_collect_time = (23.799999952316284 if sms
                              else random.randint(10, 99))
    else:
        try:
            fixed_collect_time = json.loads(str(fixed_collect_time))
        except (TypeError, ValueError, json.JSONDecodeError):
            fixed_collect_time = float(fixed_collect_time)
    custom["collectTime"] = fixed_collect_time
    ms_version = n.pop("ms_version", "0.0.0.1")
    n["custom"] = json.dumps(custom, ensure_ascii=False, separators=(",", ":"))
    n["ms_version"] = ms_version

    wid = profile.get("wID") or {}
    wid["msgType"] = 1
    wid["timestamp"] = str(now_ms)
    wid["aid"] = aid
    wid["pageId"] = page_id
    # Current Chrome 151 reports the same nap on the initial full common
    # report and on the SMS page.  Keep it configurable for old fixtures, but
    # never silently retain the stale profile value when no override exists.
    wid["nap"] = os.getenv("DY_MSTOKEN_FIXED_NAP",
                           "11311144242322244122")
    # Match Chrome's current viewport values in the top-level common report.
    prof = get_profile()
    g = prof["geo"]
    top_nav = profile.get("navigator") or {}
    top_nav.update({
        "appVersion": prof["ua"].replace("Mozilla/", "", 1),
        "deviceMemory": str(prof["device_memory"]),
        "hardwareConcurrency": int(prof["cpu_core_num"]),
    })
    profile["navigator"] = top_nav
    top_webgl = profile.get("webgl") or {}
    top_webgl.update({
        "renderer": prof["webgl_renderer"],
        "vendor": prof["webgl_vendor"],
    })
    profile["webgl"] = top_webgl
    n_nav = n.get("navigator") or {}
    n_nav.update({
        "userAgent": prof["ua"],
        "hardwareConcurrency": int(prof["cpu_core_num"]),
    })
    n["navigator"] = n_nav
    n_screen = n.get("screen") or {}
    n_screen.update({
        "height": int(prof["screen_height"]),
        "width": int(prof["screen_width"]),
        "availHeight": g[5], "availWidth": g[4],
        "availTop": 0, "availLeft": 0,
    })
    n["screen"] = n_screen
    n_webgl = n.get("webgl") or {}
    n_webgl.update({
        "renderer": prof["webgl_renderer"],
        "vendor": prof["webgl_vendor"],
    })
    n["webgl"] = n_webgl
    screen = profile.get("screen") or {}
    screen.update({
        "innerWidth": g[0], "innerHeight": g[1],
        "outerWidth": g[2], "outerHeight": g[3],
        "screenX": prof.get("screen_x", 0),
        "screenY": prof.get("screen_y", 0),
        "availWidth": g[4], "availHeight": g[5],
        "sizeWidth": g[6], "sizeHeight": g[7],
        "clientWidth": g[0], "clientHeight": g[1],
    })
    profile["screen"] = screen
    profile["nWID"] = n
    profile["wID"] = wid

    plaintext = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
    # The nonce is carried in the first two bytes of the custom base64 blob;
    # it is intentionally fresh for each report, just like Chrome.  A fixed
    # nonce is supported for byte-for-byte debug fixtures.
    if fixed_nonce is None:
        fixed_nonce = os.getenv("DY_MSTOKEN_FIXED_NONCE")
    nonce = random.randint(0, 255) if fixed_nonce is None else int(fixed_nonce)
    str_data = encode_strdata(plaintext.encode("utf-8"), nonce)
    if fixed_tsp is None:
        fixed_tsp = os.getenv("DY_MSTOKEN_FIXED_TSP")
    tsp = (now_ms + 11 if sms else now_ms + 10
           ) if fixed_tsp is None else int(fixed_tsp)
    envelope = {
        "magic": 538969122,
        "version": 1,
        "dataType": 8,
        "strData": str_data,
        "tspFromClient": tsp,
        "ulr": 0,
    }
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))


def build_common_behavior_body(fixed_timestamp=None, fixed_tsp=None,
                               fixed_nonce=None):
    """Build Chrome's periodic 783-byte `/web/common` behavior heartbeat.

    The live page emits this independently of QR status every 300 seconds.
    It carries no new full fingerprint: only ``wID.msgType=2`` and the empty
    behavior queues plus the current window/screen geometry.
    """
    if fixed_timestamp is None:
        fixed_timestamp = os.getenv("DY_MSTOKEN_FIXED_TIMESTAMP")
    now_ms = int(time.time() * 1000) if fixed_timestamp is None else int(fixed_timestamp)
    prof = get_profile()
    g = prof["geo"]
    plaintext = json.dumps({
        "wID": {
            "msgType": 2,
            "privacyMode": 0,
            "timestamp": str(now_ms),
        },
        "behavior": {
            "beMove": [],
            "beClick": [],
            "beClickEnd": [],
            "beKeyboard": [],
            "windowState": [],
            "gyro": [],
            "focus": [],
            "screen": {
                "innerWidth": g[0], "innerHeight": g[1],
                "outerWidth": g[2], "outerHeight": g[3],
                "screenX": prof.get("screen_x", 0),
                "screenY": prof.get("screen_y", 0),
                "pageXOffset": 0, "pageYOffset": 0,
                "availWidth": g[4], "availHeight": g[5],
                "sizeWidth": g[6], "sizeHeight": g[7],
                "clientWidth": g[0], "clientHeight": g[1],
                "colorDepth": 24, "pixelDepth": 24,
                "orientaionType": "landscape-primary",
                "orientaionAngle": 0,
            },
        },
    }, ensure_ascii=False, separators=(",", ":"))
    if fixed_nonce is None:
        fixed_nonce = os.getenv("DY_MSTOKEN_FIXED_NONCE")
    nonce = random.randint(0, 255) if fixed_nonce is None else int(fixed_nonce)
    if fixed_tsp is None:
        fixed_tsp = os.getenv("DY_MSTOKEN_FIXED_TSP")
    tsp = now_ms + 3 if fixed_tsp is None else int(fixed_tsp)
    return json.dumps({
        "magic": 538969122,
        "version": 1,
        "dataType": 8,
        "strData": encode_strdata(plaintext.encode("utf-8"), nonce),
        "tspFromClient": tsp,
        "ulr": 0,
    }, ensure_ascii=False, separators=(",", ":"))


def _get_ttwid(ttwid: str = None) -> str:
    if ttwid:
        return ttwid
    m = re.search(r"ttwid=([^;]+)", os.getenv("DY_COOKIES") or "")
    return m.group(1) if m else ""


def get_mstoken(ttwid: str = None, proxies: dict = None, use_cache: bool = True,
                cookie_sink=None, creator: bool = False) -> str:
    """取 msToken。creator=True 时用 ms_appid=2906 轮换（creator.douyin.com 专用）。

    浏览器 creator 页的 mssdk 轮换走 2906（token 184 字符），与主站 6383
    （164 字符）不同缓存、不同长度；creator 域的请求（发布/评论等）必须带 2906 版。
    """
    cache = _creator_cache if creator else _cache
    if use_cache and cache["token"] and (time.time() - cache["ts"] < _TTL):
        return cache["token"]

    envelope = build_report_body()
    url = _CREATOR_TOKEN_URL if creator else _TOKEN_URL
    # ``mssdk.bytedance.com`` is cross-site from the Douyin page.  Keep the
    # full Chrome 151 header set; only accept-encoding/content-length are left
    # to the HTTP transport.
    headers = _mssdk_headers()
    # 续期时把旧 token 挂在 query 上（实录 reqid=408/920/937 都是这么发的）
    if cache["token"]:
        url += "&msToken=" + urllib.parse.quote(cache["token"], safe="")
    try:
        resp = requests.post(url, data=envelope.encode("utf-8"), headers=headers,
                             verify=False, timeout=25, proxies=proxies)
        if cookie_sink is not None:
            try:
                cookie_sink(resp.cookies.get_dict())
            except Exception:
                pass
        token = resp.headers.get("x-ms-token", "")
        if not token:
            m = re.search(r"msToken=([^;]+)", resp.headers.get("set-cookie", ""))
            token = m.group(1) if m else ""
        if token:
            cache["token"] = token
            cache["ts"] = time.time()
        return token
    except Exception:
        return ""


def refresh_common_mstoken(ttwid: str = None, current_token: str = "",
                           proxies: dict = None, behavior=False, sms=False,
                           cookie_sink=None) -> str:
    """Rotate the login-page token through Chrome's `/web/common` reports."""
    envelope = (build_common_behavior_body() if behavior
                else build_common_report_body(sms=sms))
    headers = _mssdk_headers(storage_access=True)
    url = _COMMON_URL + "?ms_appid=6383"
    if current_token:
        url += "&msToken=" + urllib.parse.quote(current_token, safe="")
    try:
        resp = requests.post(url, data=envelope.encode("utf-8"),
                             headers=headers, verify=False, timeout=25,
                             proxies=proxies)
        if cookie_sink is not None:
            try:
                cookie_sink(resp.cookies.get_dict())
            except Exception:
                pass
        token = resp.headers.get("x-ms-token", "")
        if not token:
            m = re.search(r"msToken=([^;]+)",
                          resp.headers.get("set-cookie", ""))
            token = m.group(1) if m else ""
        return token
    except Exception:
        return ""
