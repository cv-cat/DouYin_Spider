from enum import Enum

from utils.dy_util import generate_ree_key, generate_bd_ticket_client_data, generate_csrf_token


class HeaderType(Enum):
    DOC = 'DOC'
    POST = 'POST'
    FORM = 'FORM'
    GET = 'GET'
    PROTOBUF = 'PROTOBUF'


class Header:
    def __init__(self):
        self.headers = {}

    def with_uifid(self, auth):
        """`uifid` 头，取自 UIFID Cookie。

        2026-08-16 抓包：主站绝大多数 aweme XHR 都把 uifid 既放 query 也放请求头，
        以前只有个别接口手工设过，其余全漏了。
        """
        uifid = (auth.cookie or {}).get('UIFID', '') if auth else ''
        if uifid:
            self.set_header('uifid', uifid)
        return self

    def with_bd(self, api, auth, aid=6383, origin='https://www.douyin.com',
                timestamp=None, dtrait_timestamp=None, dtrait_randbytes=None,
                require_dtrait=False):
        """bd-ticket-guard 请求头（对齐 passport zero.js 的请求拦截器分支）。

        :param api: 请求 pathname（不含 query）。
        :param aid: 该子域的 aid，用于换取服务端证书（www=6383，creator=2906）。
        :param origin: 换证书的站点，需与业务请求同源。
        """
        from utils.bd_ticket import ticket_guard_version
        if not auth.ticket_matches_session():
            raise RuntimeError(
                'bd-ticket-guard 的 ticket/ts_sign 与当前 cookie 不是同一次登录'
                '（cookie 里的 bd_ticket_guard_ts_sign_id 对不上 DY_TS_SIGN）。'
                '强校验接口会失败且报错无从判断，请重新抓取配套的凭证。'
            )
        ecdh_key = auth.ecdh_key(aid=aid, origin=origin)
        trust_cookie = (getattr(auth, "cookie", None) or {}).get(
            "_bd_ticket_crypt_cookie"
        )
        client_data, algo_type = generate_bd_ticket_client_data(
            api, auth.ticket, auth.ts_sign, auth.private_key, ecdh_key=ecdh_key,
            timestamp=timestamp,
            t_trust=1 if trust_cookie else None,
        )
        self.set_header('bd-ticket-guard-client-data', client_data)
        self.set_header('bd-ticket-guard-ree-public-key', generate_ree_key(auth.private_key))
        self.set_header('bd-ticket-guard-version', '2')
        self.set_header('bd-ticket-guard-web-version', str(ticket_guard_version(auth.ts_sign)))
        self.set_header('bd-ticket-guard-web-sign-type', '1' if algo_type == 'hmac' else '0')
        # 浏览器在 bd-ticket-guard 之外还会带设备特征头，高风控接口（如评论）缺它会被拦
        dtrait = auth.session_dtrait_header(
            api, aid=aid, origin=origin, timestamp=dtrait_timestamp,
            randbytes=dtrait_randbytes, strict=require_dtrait,
            allow_static=not require_dtrait,
        )
        if dtrait:
            self.set_header('x-tt-session-dtrait', dtrait)
        elif require_dtrait:
            raise RuntimeError(
                '发布接口必须携带 x-tt-session-dtrait，当前未能生成'
            )
        return self

    def with_bd_readonly(self, auth):
        """只读接口的 bd-ticket-guard 头（4 个，**不含 client-data**）。

        2026-08-16 实录（`comment/list` / `aweme/favorite` / `user/following/list`）
        headers_wire 里只有这四个：
            bd-ticket-guard-ree-public-key / -version: 2 /
            -web-sign-type / -web-version: 2

        与发布类接口（`create_v2` / `comment/publish`）的区别：那些**额外带
        `bd-ticket-guard-client-data`**（里面含对本次请求 path+ticket+timestamp
        的签名），走 `with_bd()`。只读接口浏览器不发 client-data，
        我们也不能自作主张加——多字段同样是与浏览器不一致。

        `web-sign-type` 由客户端证书格式决定：`pub.<b64>` 新版证书且能拿到
        服务端证书时是 hmac(=1)，否则 ECDSA 兜底(=0)。这里按 auth 的实际
        凭证算，与 `with_bd()` 用同一套判定，保证同一会话下取值自洽。
        """
        from utils.bd_ticket import ticket_guard_version
        try:
            if not getattr(auth, 'private_key', None):
                return self
            self.set_header('bd-ticket-guard-ree-public-key',
                            generate_ree_key(auth.private_key))
            self.set_header('bd-ticket-guard-version', '2')
            self.set_header('bd-ticket-guard-web-version',
                            str(ticket_guard_version(getattr(auth, 'ts_sign', '') or '')))
            algo = 'hmac' if str(getattr(auth, 'client_cert', '') or '').startswith('pub.') else 'ecdsa'
            self.set_header('bd-ticket-guard-web-sign-type', '1' if algo == 'hmac' else '0')
        except Exception:
            pass
        return self

    def with_session_dtrait(self, api, auth, aid=6383,
                            origin='https://www.douyin.com',
                            timestamp=None, randbytes=None):
        """Attach the path-bound dtrait header required by write endpoints.

        A complete ``DY_SESSION_DTRAIT`` capture is intentionally not accepted
        here: its encrypted payload is tied to one pathname and timestamp.
        The inner blob must come from ``dtrait_blob`` or ``dtrait_profile`` so
        the outer header can be rebuilt for this request.
        """
        dtrait = auth.session_dtrait_header(
            api, aid=aid, origin=origin, timestamp=timestamp,
            randbytes=randbytes, strict=True, allow_static=False,
        )
        self.set_header('x-tt-session-dtrait', dtrait)
        return self

    def set_header(self, key, value):
        self.headers[key] = value
        return self

    def with_csrf(self, cookie_str):
        self.set_header('x-secsdk-csrf-token', generate_csrf_token(cookie_str)[0])

    def set_referer(self, url):
        self.set_header('referer', url)
        return self

    def remove_header(self, key):
        if key in self.headers:
            del self.headers[key]
        return self

    def get(self):
        return self.headers

    def __call__(self):
        return self.headers


class HeaderBuilder:
    from utils.fingerprint import get_profile
    ua = get_profile()["ua"]
    sec_ch_ua = get_profile()["sec_ch_ua"]
    sec_ch_ua_platform = get_profile()["sec_ch_ua_platform"]
    accept_language = get_profile()["accept_language"]

    @staticmethod
    def build(header_type):
        """XHR 请求头，对齐浏览器实录。

        `sec-ch-ua` / `-mobile` / `-platform` **必须发**：这三个一度被删掉，
        依据是 CDP `Network.requestWillBeSent` 里看不到它们 —— 但那个事件只给
        页面 JS 设的头，浏览器网络层后加的要看 `requestWillBeSentExtraInfo`。
        补上 extraInfo 重抓后确认，主站 aweme XHR 是**带**这三个的。
        同理 `accept-language` / `priority` / `sec-fetch-*` 也确实要发。

        不发的是 `cache-control` / `pragma`（实录里确实没有）。
        `accept-encoding` / `cookie` / `content-length` 由 HTTP 层自己补。
        """
        header = Header()
        header.set_header('user-agent', HeaderBuilder.ua)
        if header_type == HeaderType.POST:
            header.set_header('accept', '*/*')
            header.set_header('content-type', 'application/json; charset=UTF-8')
        elif header_type == HeaderType.FORM:
            header.set_header('accept', 'application/json, text/plain, */*')
            header.set_header('content-type', 'application/x-www-form-urlencoded; charset=UTF-8')
        elif header_type == HeaderType.PROTOBUF:
            header.set_header('accept', 'application/x-protobuf')
            header.set_header('content-type', 'application/x-protobuf')
        elif header_type == HeaderType.GET:
            header.set_header('accept', 'application/json, text/plain, */*')
        elif header_type == HeaderType.DOC:
            header = Header()
            h = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'accept-language': HeaderBuilder.accept_language,
                'cache-control': 'no-cache',
                'cookie': '',
                'pragma': 'no-cache',
                'priority': 'u=0, i',
                'sec-ch-ua': HeaderBuilder.sec_ch_ua,
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': HeaderBuilder.sec_ch_ua_platform,
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'none',
                'sec-fetch-user': '?1',
                'upgrade-insecure-requests': '1',
                'user-agent': HeaderBuilder.ua
            }
            header.headers.update(h)
            return header
        # 非 DOC 的 XHR 统一补上这几个，顺序照浏览器
        header.set_header('sec-ch-ua', HeaderBuilder.sec_ch_ua)
        header.set_header('sec-ch-ua-mobile', '?0')
        header.set_header('sec-ch-ua-platform', HeaderBuilder.sec_ch_ua_platform)
        header.set_header('accept-language', HeaderBuilder.accept_language)
        header.set_header('priority', 'u=1, i')
        header.set_header('sec-fetch-dest', 'empty')
        header.set_header('sec-fetch-mode', 'cors')
        header.set_header('sec-fetch-site', 'same-origin')
        return header
