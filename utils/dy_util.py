import hashlib
import re
import time
import json
import random
import base64
import urllib

import requests
requests.packages.urllib3.disable_warnings()
from utils.fingerprint import get_profile


def trans_cookies(cookies_str):
    cookies = {
        # "douyin.com": "",
    }
    for i in cookies_str.split("; "):
        try:
            cookies[i.split('=')[0]] = '='.join(i.split('=')[1:])
        except:
            continue
    # cookies = {i.split('=')[0]: '='.join(i.split('=')[1:]) for i in cookies_str.split('; ')}
    return cookies


# 私信传obj, 其他的拼接
def generate_req_sign(e, priK):
    """bd-ticket-guard ECDSA req_sign。"""
    from utils.bd_ticket import get_req_sign
    return get_req_sign(e, priK)


# query, data都是拼接字符串
def generate_a_bogus(query, data=""):
    """a_bogus。"""
    return _pure_sign().sign(f'https://www.douyin.com/?{query}', data)


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
def generate_bd_ticket_client_data(api, ticket, ts_sign, priK):
    timestamp = int(time.time())
    res_sign = f"ticket={ticket}&path={api}&timestamp={timestamp}"
    p = {
        'ts_sign': ts_sign,
        'req_content': 'ticket,path,timestamp',
        'req_sign': generate_req_sign(res_sign, priK),
        'timestamp': timestamp,
    }
    p = json.dumps(p, ensure_ascii=False, separators=(',', ':'))
    return base64.urlsafe_b64encode(p.encode('utf-8')).decode('utf-8')


def generate_msToken(randomlength=107):
    random_str = ''
    base_str = 'ABCDEFGHIGKLMNOPQRSTUVWXYZabcdefghigklmnopqrstuvwxyz0123456789='
    length = len(base_str) - 1
    for _ in range(randomlength):
        random_str += base_str[random.randint(0, length)]
    return random_str


def generate_dynamic_msToken(ttwid=None, proxies=None):
    """msToken"""
    try:
        from utils.mstoken import get_mstoken
        return get_mstoken(ttwid=ttwid, proxies=proxies) or ''
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



def generate_csrf_token(cookies_str):
    csrf_token_1, csrf_token_2 = None, None
    try:
        headers = {
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'cache-control': 'no-cache',
            'cookie': cookies_str,
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.douyin.com/?recommend=1',
            'sec-ch-ua': get_profile()["sec_ch_ua"],
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': get_profile()["sec_ch_ua_platform"],
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': get_profile()["ua"],
            'x-secsdk-csrf-request': '1',
            'x-secsdk-csrf-version': '1.2.22',
        }
        response = requests.head('https://www.douyin.com/service/2/abtest_config/', headers=headers, verify=False)
        return response.headers['X-Ware-Csrf-Token'].split(',')[1], response.headers['X-Ware-Csrf-Token'].split(',')[4]
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
        splice_url_str += key + '=' + urllib.parse.quote(str(value)) + '&'
    return splice_url_str[:-1]
