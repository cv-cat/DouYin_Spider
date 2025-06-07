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

    def with_bd(self, api, auth):
        self.set_header('bd-ticket-guard-client-data', generate_bd_ticket_client_data(api, auth.ticket, auth.ts_sign, auth.private_key))
        self.set_header('bd-ticket-guard-iteration-version', '1')
        self.set_header('bd-ticket-guard-ree-public-key', generate_ree_key(auth.private_key))
        self.set_header('bd-ticket-guard-version', '2')
        self.set_header('bd-ticket-guard-web-version', '1')

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
    # ua = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 '
    #       'Safari/537.36 Edg/125.0.0.0')
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0"

    @staticmethod
    def build(header_type):
        header = Header()
        header.set_header('user-agent', HeaderBuilder.ua)
        header.set_header('cache-control', 'no-cache')
        header.set_header('pragma', 'no-cache')
        header.set_header('sec-ch-ua', '"Microsoft Edge";v="125", "Chromium";v="125", "Not.A/Brand";v="24"')
        header.set_header('sec-ch-ua-mobile', '?0')
        header.set_header('sec-ch-ua-platform', '"Windows"')
        header.set_header('sec-fetch-dest', 'empty')
        header.set_header('sec-fetch-mode', 'cors')
        header.set_header('sec-fetch-site', 'same-origin')
        header.set_header('priority', 'u=1, i')
        header.set_header('accept-language', 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6')
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
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                'cache-control': 'no-cache',
                'cookie': '',
                'pragma': 'no-cache',
                'priority': 'u=0, i',
                'sec-ch-ua': '"Microsoft Edge";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'none',
                'sec-fetch-user': '?1',
                'upgrade-insecure-requests': '1',
                'user-agent': HeaderBuilder.ua
            }
            header.headers.update(h)
        return header
