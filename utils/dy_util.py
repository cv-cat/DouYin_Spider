import hashlib
import os
import re
import time
import json
import random
import base64
import urllib

from utils import http_client as requests
requests.packages.urllib3.disable_warnings()
from utils.fingerprint import get_profile


class CookieDict(dict):
    """Cookie mapping with a sidecar for Chromium's bare cookie tokens.

    DevTools occasionally shows a domain token such as ``douyin.com`` without
    an equals sign.  A normal ``dict`` cannot represent that wire item without
    turning it into the different ``douyin.com=`` pair, so keep the token
    names out-of-band while retaining normal mapping behaviour for callers.
    """

    def __init__(self, *args, raw_tokens=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_tokens = list(raw_tokens or ())
        # Optional back-reference used by the unified HTTP adapter.  Keeping
        # this on the CookieDict lets legacy ``requests.get(...,
        # cookies=auth.cookie)`` call sites transparently reuse the owning
        # Auth Session without changing every API method signature.
        self._auth_owner = None


def trans_cookies(cookies_str):
    """Cookie 串转 dict。

    空串 / 多余分号会切出空片段，早先的写法会塞进一个键为 '' 的条目，
    requests 发出去就是个畸形的 `=value`，这里直接跳过。
    """
    cookies = CookieDict()
    raw_tokens = []
    for item in (cookies_str or '').split(';'):
        name, sep, value = item.strip().partition('=')
        if not name:
            continue
        if not sep:
            # Preserve a bare token exactly for the later wire serializer.
            raw_tokens.append(name)
            continue
        cookies[name] = value
    cookies.raw_tokens = raw_tokens
    return cookies


def bind_cookie_owner(cookie, owner):
    """Attach an Auth owner to a cookie mapping when possible.

    Some bootstrap paths historically used a plain ``dict`` and therefore
    could not participate in the compatibility HTTP bridge.  This helper is
    intentionally best-effort so callers can keep accepting ordinary mappings.
    """
    try:
        cookie._auth_owner = owner
    except Exception:
        pass
    return cookie


# 私信传obj, 其他的拼接
def generate_req_sign(e, priK):
    """bd-ticket-guard ECDSA req_sign。"""
    from utils.bd_ticket import get_req_sign
    return get_req_sign(e, priK)


# query, data都是拼接字符串
def generate_a_bogus(query, data="", host="www.douyin.com"):
    """a_bogus。host 决定签名里内嵌的 (aid, page_id)，各子域不同。"""
    return _pure_sign().sign_query(query, data, host=host)


def generate_signature(room_id, user_unique_id):
    """直播 X-Bogus。"""
    raw_string = f"live_id=1,aid=6383,version_code=180800,webcast_sdk_version=1.0.15,room_id={room_id},sub_room_id=,sub_channel_id=,did_rule=3,user_unique_id={user_unique_id},device_platform=web,device_type=,ac=,identity=audience"
    x_ms_stub = hashlib.md5(raw_string.encode("utf-8")).hexdigest()
    return _xb_sign().sign(x_ms_stub)


# 传递私钥
def generate_ree_key(prik):
    """bd-ticket-guard """
    from utils.bd_ticket import get_ree_key
    return get_ree_key(prik)


# 传递query, ticket, ts_sign, priK
def generate_bd_ticket_client_data(api, ticket, ts_sign, priK, ecdh_key=None,
                                   timestamp=None, t_trust=None):
    """:return: (client_data_b64, algo_type)"""
    from utils.bd_ticket import generate_bd_ticket_client_data as _gen
    return _gen(
        api, ticket, ts_sign, priK, ecdh_key=ecdh_key, timestamp=timestamp,
        t_trust=t_trust,
    )


def generate_msToken(randomlength=107):
    random_str = ''
    base_str = 'ABCDEFGHIGKLMNOPQRSTUVWXYZabcdefghigklmnopqrstuvwxyz0123456789='
    length = len(base_str) - 1
    for _ in range(randomlength):
        random_str += base_str[random.randint(0, length)]
    return random_str


def generate_dynamic_msToken(ttwid=None, proxies=None, creator=False):
    """msToken（creator=True 走 ms_appid=2906，creator.douyin.com 专用 184 字符版）"""
    try:
        from utils.mstoken import get_mstoken
        return get_mstoken(ttwid=ttwid, proxies=proxies, creator=creator) or ''
    except Exception:
        return ''


_pure_signer = None
_xb_signer = None


def _pure_sign():
    global _pure_signer
    if _pure_signer is None:
        from utils.ab_pure import ABogusPureSigner
        _pure_signer = ABogusPureSigner(fixed=False)
    return _pure_signer


def _xb_sign():
    global _xb_signer
    if _xb_signer is None:
        from utils.xbogus_pure import XbogusSigner
        _xb_signer = XbogusSigner()
    return _xb_signer


def generate_a_bogus_pure(api_path, query):
    """a_bogus"""
    return _pure_sign().sign(f'https://www.douyin.com{api_path}?{query}')



_SV_CHARSET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'


def generate_s_v_web_id():
    """生成 s_v_web_id（同时用作 query 里的 verifyFp / fp）。

    实测格式：``verify_<base36 毫秒时间戳>_<8>_<4>_<4>_<4>_<12>``，
    后五组是 UUID v4 的形状（第 3 组固定 '4' 开头，第 4 组取 8/9/a/b），
    但每位从 62 字符表里取，而不是十六进制。
    """
    fixed = os.getenv("DY_FIXED_SV_WEB_ID") or os.getenv("DY_FIXED_WEB_ID")
    if fixed:
        return fixed
    n, ts36 = int(time.time() * 1000), ''
    while n:
        n, r = divmod(n, 36)
        ts36 = '0123456789abcdefghijklmnopqrstuvwxyz'[r] + ts36

    def rnd(k):
        return ''.join(random.choice(_SV_CHARSET) for _ in range(k))

    groups = [rnd(8), rnd(4), '4' + rnd(3), random.choice('89ab') + rnd(3), rnd(12)]
    return 'verify_' + ts36 + '_' + '_'.join(groups)


def generate_fake_webid(random_length=19):
    random_str = ''
    base_str = '0123456789'
    length = len(base_str) - 1
    for _ in range(random_length):
        random_str += base_str[random.randint(0, length)]
    return random_str


def generate_webid(auth=None, url=""):
    if url == "":
        url = f"https://www.douyin.com/discover?modal_id=7376449060384935209"
    try:
        from builder.header import HeaderBuilder, HeaderType
        headers = HeaderBuilder().build(HeaderType.DOC)
        headers.set_header('cookie', auth.cookie_str if auth else "")
        headers.set_header("upgrade-insecure-requests", "1")
        response = requests.get(url, headers=headers.get(), verify=False)
        res_text = response.text
        user_unique_id = re.findall(r'\\"user_unique_id\\":\\"(.*?)\\"', res_text)[0]
        webid = user_unique_id
        return webid
    except Exception as e:
        # print("===================")
        # print(url)
        # print(e)
        # print("===================")
        return generate_fake_webid()



def generate_csrf_token(cookies_str, origin='https://www.douyin.com',
                        path='/service/2/abtest_config/', referer=None):
    """向站点换取 `x-secsdk-csrf-token`（响应头 `X-Ware-Csrf-Token`）。

    **必须按子域取**：csrf token 与 `csrf_session_id` 绑定，creator 域拿 www 域的
    token 会校验不过。2026-08-16 实录，creator 页面用的是
    `HEAD https://creator.douyin.com/web/api/media/anchor/search`。

    实录的 HEAD 请求头只有 6 个，且 **不带** `sec-ch-ua*` / `cache-control` /
    `pragma`（以前无条件加了这五个）；顺序照抄浏览器：
    `x-secsdk-csrf-request` → `referer` → `user-agent` → `x-secsdk-csrf-version`
    → `accept` → `accept-language`。

    :return: (token_1, token_2) —— 取响应头逗号分隔的第 1 段与第 4 段。
    """
    csrf_token_1, csrf_token_2 = None, None
    try:
        headers = {
            'x-secsdk-csrf-request': '1',
            'referer': referer or (origin + '/'),
            'user-agent': get_profile()["ua"],
            'x-secsdk-csrf-version': '1.2.22',
            'accept': '*/*',
            'accept-language': get_profile()["accept_language"],
        }
        response = requests.head(origin + path, headers=headers,
                                 cookies=trans_cookies(cookies_str), verify=False)
        parts = response.headers['X-Ware-Csrf-Token'].split(',')
        return parts[1], parts[4]
    except Exception as e:
        return csrf_token_1, csrf_token_2


def generate_millisecond():
    millis = int(round(time.time() * 1000))
    return millis


def splice_url(params):
    splice_url_str = ''
    for key, value in params.items():
        if value is None:
            value = ''
        # URLSearchParams/fetch encodes '/' in form/query values as %2F.
        # Leaving the slash safe makes the a_bogus input differ from the
        # bytes that actually go over the wire (notably body `next=https://...`).
        splice_url_str += key + '=' + urllib.parse.quote(str(value), safe='') + '&'
    return splice_url_str[:-1]
