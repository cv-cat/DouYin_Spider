import re
import sys
import time
import json
import random
import base64
import urllib
from os import path

import requests
requests.packages.urllib3.disable_warnings()
import subprocess
from functools import partial

subprocess.Popen = partial(subprocess.Popen, encoding="utf-8")
import execjs

if getattr(sys, 'frozen', None):
    basedir = sys._MEIPASS
else:
    basedir = path.dirname(__file__)


try:
    node_modules = path.join(basedir, 'node_modules')
    dy_path = path.join(basedir, 'static', 'dy_ab.js')
    dy_js = execjs.compile(open(dy_path, 'r', encoding='utf-8').read(), cwd=node_modules)
    sign_path = path.join(basedir, 'static', 'dy_live_sign.js')
    sign_js = execjs.compile(open(sign_path, 'r', encoding='utf-8').read(), cwd=node_modules)
except:
    node_modules = path.join(basedir, '..', 'node_modules')
    dy_path = path.join(basedir, '..', 'static', 'dy_ab.js')
    dy_js = execjs.compile(open(dy_path, 'r', encoding='utf-8').read(), cwd=node_modules)
    sign_path = path.join(basedir, '..', 'static', 'dy_live_sign.js')
    sign_js = execjs.compile(open(sign_path, 'r', encoding='utf-8').read(), cwd=node_modules)


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
    sign = dy_js.call('get_req_sign', e, priK)
    return sign


# query, data都是拼接字符串
def generate_a_bogus(query, data=""):
    a_bogus = dy_js.call('get_ab', query, data)
    return a_bogus


def generate_signature(roomId, user_unique_id):
    return sign_js.call('sign', roomId, user_unique_id)


# 传递私钥
def generate_ree_key(prik):
    ree_key = dy_js.call('get_ree_key', prik)
    return ree_key


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


def generate_ttwid():
    url = f"https://www.douyin.com/discover?modal_id=7376449060384935209"
    ttwid = None
    try:
        headers = {
            'user-agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
        }
        response = requests.get(url, headers=headers, verify=False)
        cookies_dict = response.cookies.get_dict()
        ttwid = cookies_dict.get('ttwid')
        return ttwid
    except Exception as e:
        return ttwid


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


def ws_accept_key(ws_key):
    """calc the Sec-WebSocket-Accept key by Sec-WebSocket-key
    come from client, the return value used for handshake

    :ws_key: Sec-WebSocket-Key come from client
    :returns: Sec-WebSocket-Accept

    """
    import hashlib
    import base64
    try:
        magic = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
        sha1 = hashlib.sha1()
        sha1.update(ws_key + magic)
        return base64.b64encode(sha1.digest())
    except Exception as e:
        return None


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
            'sec-ch-ua': '"Microsoft Edge";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
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
