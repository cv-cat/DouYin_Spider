import base64
import hashlib
import json
import random
import re
import time
import urllib
import uuid

from utils import http_client as requests
requests.packages.urllib3.disable_warnings()
from bs4 import BeautifulSoup
from loguru import logger
from google.protobuf.json_format import MessageToDict as _message_to_dict


def protobuf_to_dict(message):
    return _message_to_dict(message, preserving_proto_field_name=True)

import static.Response_pb2 as ResponseProto
from builder.header import HeaderBuilder, HeaderType
from builder.params import Params
from builder.proto import ProtoBuilder
from utils.fingerprint import get_profile
from utils.dy_util import splice_url, generate_a_bogus, generate_msToken, trans_cookies, generate_a_bogus_pure

# a_bogus 签名里内嵌 (aid, page_id)，按子域取值，走 live 域的接口必须显式指定
LIVE_HOST = 'live.douyin.com'



def check_risk_response(resp):
    """抖音风控拒绝时返回 HTTP 200 + 空 body 或 HTML 挑战页，原因只在响应头里，
    这里翻译成可读异常。直接 `resp.json()` 只会得到毫无信息量的 JSONDecodeError。
    """
    text = (resp.text or "").lstrip()
    if text.startswith("{") or text.startswith("["):
        return
    bd = resp.headers.get("X-Vc-Bdturing-Parameters")
    if bd:
        subtype = ""
        try:
            info = json.loads(base64.b64decode(bd + "=" * (-len(bd) % 4)))
            subtype = info.get("subtype", "")
        except Exception:
            pass
        raise RuntimeError(
            f"触发人机验证（bdturing {subtype or '未知类型'}）。"
            f"需在浏览器完成验证、或更换 IP / 降低请求频率后重试。logid={resp.headers.get('X-Tt-Logid')}")
    pp = resp.headers.get("X-Tt-Verify-Passport-Decision")
    if pp:
        scene = ""
        try:
            scene = json.loads(pp)["event_params"]["verify_scene"]
        except Exception:
            pass
        raise RuntimeError(
            f"需要二次身份验证（scene={scene or '未知'}）。"
            f"多为缺少 x-tt-session-dtrait 或账号风控所致。logid={resp.headers.get('X-Tt-Logid')}")
    if not text:
        raise RuntimeError(
            f"接口返回空响应（HTTP {resp.status_code}），通常是签名参数不对或被风控拦截。"
            f"logid={resp.headers.get('X-Tt-Logid')}")
    if "__ac_nonce" in text or "_$jsvmprt" in text:
        raise RuntimeError(
            f"命中 acrawler 挑战页（HTTP {resp.status_code}）。需要 __ac_signature，"
            f"该签名尚未纯算实现。logid={resp.headers.get('X-Tt-Logid')}")
    raise RuntimeError(
        f"接口返回非 JSON（HTTP {resp.status_code}），前 120 字：{text[:120]!r}。"
        f"logid={resp.headers.get('X-Tt-Logid')}")


def parse_aweme_id(url: str):
    """从作品链接里取 aweme_id，并归一化成 /video/ 形式的 referer。

    支持 `/video/<id>`、`/note/<id>`（图文）与带 `modal_id=<id>` 的链接。
    """
    m = re.search(r'/(?:video|note|slides)/(\d+)', url) or re.search(r'modal_id=(\d+)', url)
    if not m:
        raise ValueError(f"无法从链接中解析 aweme_id: {url}")
    aweme_id = m.group(1)
    return aweme_id, f'https://www.douyin.com/video/{aweme_id}'


class DouyinAPI:
    douyin_url = 'https://www.douyin.com'
    live_url = 'https://live.douyin.com'
    creator = "https://creator.douyin.com"

    # Current PC IM business message types (the protobuf field is an integer;
    # payload remains a JSON string).  Keep these public for callers building
    # less common card variants.
    IM_TEXT = 7
    IM_BIG_EMOJI = 5
    IM_STORY_PICTURE = 27
    IM_STORY_VIDEO = 30
    IM_VOICE = 17
    IM_ENCRYPT_VOICE = 109
    IM_SHARE_AWEME = 8
    IM_SHARE_PHOTOS = 77
    IM_SHARE_WEB = 26
    IM_SHARE_USER = 25
    IM_FILE = 6


    @staticmethod
    def get_user_all_work_info(auth, user_url: str, **kwargs) -> list:
        """
        获取用户全部作品信息.
        :param auth: DouyinAuth object.
        :param user_url: 用户主页URL.
        :return: 全部作品信息.
        """
        max_cursor = "0"
        work_list = []
        while True:
            res_json = DouyinAPI.get_user_work_info(auth, user_url, max_cursor)
            if "aweme_list" not in res_json.keys():
                break
            works = res_json["aweme_list"]
            max_cursor = str(res_json["max_cursor"])
            work_list.extend(works)
            if res_json["has_more"] != 1:
                break
        return work_list


    @staticmethod
    def get_user_work_info(auth, user_url: str, max_cursor, **kwargs) -> dict:
        """
        获取用户作品信息.
        :param auth: DouyinAuth object.
        :param user_url:  用户主页URL.
        :param max_cursor:  上一次请求的max_cursor.
        :return:
        """
        api = f"/aweme/v1/web/aweme/post/"
        user_id = user_url.split("/")[-1].split("?")[0]
        headers = HeaderBuilder().build(HeaderType.GET)
        headers.set_referer(user_url)
        headers.with_uifid(auth)
        # 字段与顺序照 2026-08-16 抓包（46 项）。注意几处只能看抓包才知道的细节：
        #   - version_code 是 290100 / 29.1.0，**这个接口特有**，不是主站通用的 170400
        #   - whale_cut_token 是**空值字段**，浏览器确实发（`whale_cut_token=`）。
        #     早先误判成"浏览器不发"并删掉了，根因是 parse_qsl 默认 keep_blank_values=False
        #     会把空值字段整个丢掉，对账脚本因此看不见它 —— 比对 query 一定要开 keep_blank_values
        #   - verifyFp / fp 在 **a_bogus 之后**（aweme/detail 那边却在之前，逐接口不同）
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("sec_user_id", user_id)
        params.add_param("max_cursor", max_cursor)
        params.add_param("locate_query", 'false')
        params.add_param("show_live_replay_strategy", '1')
        params.add_param("need_time_list", '1' if max_cursor == '0' else '0')
        params.add_param("time_list_query", '0')
        params.add_param("whale_cut_token", '')
        params.add_param("cut_version", '1')
        params.add_param("count", '18')
        params.add_param("publish_video_strategy_type", '2')
        # 实录：自己主页发 0、他人主页发 1。写死 0 去爬别人的作品与浏览器不一致，
        # 这里按 sec_user_id 是否是登录者本人来取（拿不到自己的 sec_uid 就按他人算）。
        _own = getattr(auth, 'sec_uid', None) or getattr(auth, '_sec_uid', None)
        params.add_param("from_user_page", '0' if (_own and _own == user_id) else '1')
        params.add_param("update_version_code", '170400')
        params.add_param("pc_client_type", '1')
        params.add_param("pc_libra_divert", 'Windows')
        params.add_param("support_h265", '1')
        params.add_param("support_dash", '1')
        params.add_param("cpu_core_num", get_profile()["cpu_core_num"])
        params.add_param("version_code", '290100')
        params.add_param("version_name", '29.1.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", get_profile()["screen_width"])
        params.add_param("screen_height", get_profile()["screen_height"])
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", get_profile()["browser_name"])
        params.add_param("browser_version", get_profile()["browser_version"])
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", get_profile()["engine_version"])
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("device_memory", get_profile()["device_memory"])
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        params.add_param("round_trip_time", '0')
        params.with_web_id(auth, user_url)
        params.with_uifid(auth)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        params.with_verify_fp(auth)
        # 这个接口在 secsdk 的 webSign 策略表里，末尾还要带 timestamp + 签名
        resp = requests.get(params.signed_url(f'{DouyinAPI.douyin_url}{api}', auth),
                            headers=headers.get(), cookies=auth.cookie, verify=False)
        check_risk_response(resp)
        result = resp.json()
        if hasattr(auth, "main_read_verified"):
            auth.main_read_verified = True
        return result

    @staticmethod
    def get_work_info(auth, url: str) -> dict:
        """
        获取作品信息.
        :param auth: DouyinAuth object.
        :param url: 作品URL.
        :return: JSON.
        """
        api = f"/aweme/v1/web/aweme/detail/"
        aweme_id, url = parse_aweme_id(url)
        headers = HeaderBuilder().build(HeaderType.GET)
        headers.set_referer(url)
        headers.with_uifid(auth)
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("aweme_id", aweme_id)
        # 实录里 aweme_id 之后紧跟这两个，缺了会少字段（2026-08-16 抓包）
        params.add_param("request_source", "600")
        params.add_param("origin_type", "video_page")
        # 公共组用 with_platform()：字段/顺序与浏览器同源接口一致，
        # 手写那版缺 pc_libra_divert / support_* ，会触发风控。
        # 但 version_code 必须回到 190500/19.5.0 —— 实录里 aweme/detail 就是这个值
        # （2026-08-22 用 browser_capture.json 做值层面对账时发现：上一轮换
        #  with_platform() 时把它一起降成了通用的 170400，属于自己引入的回退）。
        # version_code 是**按接口**取值的，不是全站一个常量：实录 63 条里
        # 59 条是 170400，但 aweme/detail=190500、aweme/post=290100、
        # general/search/single=190600，各自前端模块自带版本号。
        params.with_platform(round_trip_time='50', version_code='190500',
                             version_name='19.5.0')
        params.with_web_id(auth, url)
        params.with_uifid(auth)
        # 这个接口的 verifyFp / fp 在 msToken **之前**（各接口位置不同，以抓包为准）
        params.with_verify_fp(auth)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        # 这个接口在 secsdk 的 webSign 策略表里，末尾还要带 timestamp + 签名
        resp = requests.get(params.signed_url(f'{DouyinAPI.douyin_url}{api}', auth),
                            headers=headers.get(), cookies=auth.cookie, verify=False)
        check_risk_response(resp)
        result = resp.json()
        if hasattr(auth, "main_read_verified"):
            auth.main_read_verified = True
        return result

    @staticmethod
    def get_work_out_comment(auth, url: str, cursor: str = '0', **kwargs) -> dict:
        """
        获取作品的全部一级评论.
        :param auth: DouyinAuth object.
        :param url: 作品URL.
        :param cursor: 评论游标.
        :return: JSON.
        """
        api = f"/aweme/v1/web/comment/list/"
        aweme_id, url = parse_aweme_id(url)
        headers = HeaderBuilder().build(HeaderType.GET)
        headers.set_referer(url)
        headers.with_uifid(auth)
        # 浏览器在这个接口上**带 bd-ticket-guard 全套**（2026-08-16 实录 headers_wire 确认）
        headers.with_bd_readonly(auth)
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("aweme_id", aweme_id)
        params.add_param("cursor", cursor)
        params.add_param("count", "5")
        params.add_param("item_type", "0")
        # whale_cut_token / rcFT 是**空值字段**，浏览器确实发（`whale_cut_token=&...&rcFT=`）。
        # 别再用 parse_qsl 的默认行为去判断"浏览器发没发"——它会静默丢掉空值字段。
        params.add_param("whale_cut_token", "")
        params.add_param("cut_version", "1")
        params.add_param("rcFT", "")
        # 公共组改用 with_platform()：手写那版缺 pc_libra_divert / support_h265 / support_dash
        params.with_platform(round_trip_time='0')
        params.with_web_id(auth, url)
        params.with_uifid(auth)
        params.with_verify_fp(auth)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        check_risk_response(resp)
        resp_json = resp.json()
        return resp_json

    @staticmethod
    def get_work_all_out_comment(auth, url: str, **kwargs) -> list:
        """
        获取作品全部一级评论.
        :param auth: DouyinAuth object.
        :param url: 作品URL.
        :return:
        """
        cursor = "0"
        comment_list = []
        while True:
            res_json = DouyinAPI.get_work_out_comment(auth, url, cursor)
            comments = res_json["comments"]
            cursor = str(res_json["cursor"])
            if comments is None or len(comments) == 0:
                break
            comment_list.extend(comments)
            if res_json["has_more"] != 1:
                break
        return comment_list

    @staticmethod
    def get_work_inner_comment(auth, comment: dict, cursor: str, count: str = '3', **kwargs):
        """
        获取作品评论的二级评论.
        :param count: 要获取的二级评论数量.
        :param auth: DouyinAuth object.
        :param comment: 一级评论信息.
        :param cursor: 评论游标.
        :return:
        """
        api = f"/aweme/v1/web/comment/list/reply/"
        aweme_id = comment['aweme_id']
        comment_id = comment['cid']
        headers = HeaderBuilder().build(HeaderType.GET)
        refer = f'https://www.douyin.com/video/{aweme_id}'
        headers.set_referer(refer)
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("item_id", aweme_id)
        params.add_param("comment_id", comment_id)
        params.add_param("cut_version", "1")
        params.add_param("cursor", cursor)
        params.add_param("count", count)
        params.add_param("item_type", "0")
        # 这个端点**严格校验 a_bogus**（少数几个之一），签名输入必须和浏览器逐字节一致：
        #   - 公共组用 with_platform()，老的手写参数组缺 pc_libra_divert/support_*
        #   - **不带 uifid**
        #   - verifyFp / fp 放在 a_bogus **之后**，不参与签名
        # 三者错一个就会被判 bdturing（2026-08-16 用浏览器实录逐项比对确认）
        params.with_platform(round_trip_time='0')
        params.with_web_id(auth, refer)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        check_risk_response(resp)
        resp_json = resp.json()
        return resp_json

    @staticmethod
    def get_work_all_inner_comment(auth, comment: dict, **kwargs) -> list:
        """
        获取作品评论的全部二级评论.
        :param auth: DouyinAuth object.
        :param comment: 一级评论信息.
        :return: 二级评论列表.
        """
        cursor = "0"
        count = '5'
        comment_list = []
        while True:
            res_json = DouyinAPI.get_work_inner_comment(auth, comment, cursor, count)
            comments = res_json["comments"]
            cursor = str(res_json["cursor"])
            if type(comments) is list and len(comments) > 0:
                comment_list.extend(comments)
            if res_json["has_more"] != 1:
                break
        return comment_list

    @staticmethod
    def get_work_all_comment(auth, url: str, **kwargs):
        """
        获取作品全部评论.
        :param auth: DouyinAuth object.
        :param url: 作品URL.
        :return: 全部评论列表.
        """
        out_comment_list = DouyinAPI.get_work_all_out_comment(auth, url)
        for comment in out_comment_list:
            comment['reply_comment'] = []
            if comment['reply_comment_total'] > 0:
                inner_comment_list = DouyinAPI.get_work_all_inner_comment(auth, comment)
                comment['reply_comment'] = inner_comment_list
        return out_comment_list

    @staticmethod
    def get_user_info(auth, user_url: str, **kwargs) -> dict:
        """
        获取用户信息.
        :param auth: DouyinAuth object.
        :param user_url: 用户主页URL.
        :return: 用户信息.
        """
        api = f"/aweme/v1/web/user/profile/other/"
        user_id = user_url.split("/")[-1].split("?")[0]
        headers = HeaderBuilder().build(HeaderType.GET)
        headers.set_referer(user_url)
        headers.with_uifid(auth)
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("publish_video_strategy_type", '2')
        params.add_param("source", 'channel_pc_web')
        params.add_param("sec_user_id", user_id)
        params.add_param("personal_center_strategy", '1')
        # 2026-08-16 用户真实 Chrome 实录：personal_center_strategy 之后还有这两个，以前全漏了
        params.add_param("profile_other_record_enable", '1')
        params.add_param("land_to", '1')
        # 公共组换 with_platform()：手写那版缺 pc_libra_divert / support_h265 / support_dash，
        # 且 round_trip_time 写死 100（实录是 0）
        params.with_platform(round_trip_time='0')
        params.with_web_id(auth, user_url)
        params.with_uifid(auth)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        # 实录里 verifyFp / fp 在 a_bogus **之后**
        params.with_verify_fp(auth)
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        check_risk_response(resp)
        return resp.json()

    @staticmethod
    def search_general_work(auth, query: str, sort_type: str = '0', publish_time: str = '0', offset: str = '0',
                            filter_duration="", search_range="", content_type="", **kwargs):
        """
        搜索综合频道作品.
        :param auth: DouyinAuth object.
        :param query: 搜索关键字.
        :param sort_type: 排序方式 0 综合排序, 1 最多点赞, 2 最新发布.
        :param publish_time: 发布时间 0 不限, 1 一天内, 7 一周内, 180 半年内.
        :param offset: 搜索结果偏移量.
        :param filter_duration: 视频时长 空字符串 不限, 0-1 一分钟内, 1-5 1-5分钟内, 5-10000 5分钟以上
        :param search_range: 搜索范围 0 不限, 1 最近看过, 2 还未看过, 3 关注的人
        :param content_type: 内容形式 0 不限, 1 视频, 2 图文
        :return: JSON数据.
        """
        api = f"/aweme/v1/web/general/search/single/"
        headers = HeaderBuilder().build(HeaderType.GET)
        refer = f'https://www.douyin.com/search/{urllib.parse.quote(query)}?aid={uuid.uuid4()}&type=general'
        headers.set_referer(refer)
        headers.with_uifid(auth)
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("search_channel", "aweme_general")
        params.add_param("enable_history", "1")
        params.add_param("keyword", query)
        params.add_param("search_source", "normal_search")
        params.add_param("query_correct_type", "1")
        params.add_param("is_filter_search", '0' if not any(
            [sort_type != '0', publish_time != '0', filter_duration, search_range, content_type]) else '1')
        # from_group_id / pc_search_top_1_params / search_id 都是**空值字段**，
        # 浏览器确实发。实录顺序：is_filter_search → from_group_id → disable_rs
        params.add_param("from_group_id", "")
        params.add_param("disable_rs", "0")
        params.add_param("offset", offset)
        params.add_param("count", '15')
        params.add_param("need_filter_settings", '1' if offset == '0' else '0')
        params.add_param("list_type", "single")
        # 搜索页特有的两个：pc_search_top_1_params 是前端埋点上下文，search_id 翻页时才有值
        params.add_param("pc_search_top_1_params", '{"enable_ai_search_top_1":1}')
        params.add_param("search_id", kwargs.get("search_id", ""))
        # 公共组换 with_platform()：手写那版缺 pc_libra_divert / support_h265 / support_dash
        # 实录：search 系接口 version_code=190600/19.6.0，与主站通用的 170400 不同
        params.with_platform(round_trip_time='0', version_code='190600', version_name='19.6.0')
        params.with_web_id(auth, refer)
        params.with_uifid(auth)
        params.add_param("msToken", auth.msToken)
        # 综合搜索风控(antispam_check)只认新算法签名：纯算 a_bogus（Python 原生执行 bdms VMP）
        params.add_param('a_bogus', generate_a_bogus_pure(api, splice_url(params.get())))
        # 搜索接口的 verifyFp / fp 在 a_bogus **之后**（与评论接口相反，以抓包为准）
        params.with_verify_fp(auth)
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        check_risk_response(resp)
        return resp.json()

    @staticmethod
    def search_some_general_work(auth, query: str, num: int, sort_type: str, publish_time: str, filter_duration="", search_range="", content_type="", **kwargs) -> list:
        """
        搜索指定数量综合频道作品.
        :param auth: DouyinAuth object.
        :param query: 搜索关键字.
        :param num: 搜索结果数量.
        :param sort_type: 排序方式 0 综合排序, 1 最多点赞, 2 最新发布.
        :param publish_time: 发布时间 0 不限, 1 一天内, 7 一周内, 180 半年内.
        :param filter_duration: 视频时长 空字符串 不限, 0-1 一分钟内, 1-5 1-5分钟内, 5-10000 5分钟以上
        :param search_range: 搜索范围 0 不限, 1 最近看过, 2 还未看过, 3 关注的人
        :param content_type: 内容形式 0 不限, 1 视频, 2 图文
        :return: 作品列表.
        """
        offset = "0"
        work_list = []
        while True:
            res_json = DouyinAPI.search_general_work(auth, query, sort_type, publish_time, offset,
                                                     filter_duration, search_range, content_type)
            works = [w for w in res_json["data"] if w.get("aweme_info")]
            work_list.extend(works)
            if res_json["has_more"] != 1 or len(work_list) >= num:
                break
            offset = str(int(offset) + len(res_json["data"]))
        if len(work_list) > num:
            work_list = work_list[:num]
        return work_list

    @staticmethod
    def search_some_user(auth, query: str, num: int, **kwargs) -> list:
        """
        搜索指定数量用户.
        :param auth: DouyinAuth object.
        :param query: 搜索关键字.
        :param num: 搜索结果数量.
        :return: 用户列表.
        """
        offset = "0"
        count = "25"
        user_list = []
        while True:
            res_json = DouyinAPI.search_user(auth, query, offset, count)
            users = res_json["user_list"]
            user_list.extend(users)
            if res_json["has_more"] != 1 or len(user_list) >= num:
                break
            offset = str(int(offset) + int(count))
        if len(user_list) > num:
            user_list = user_list[:num]
        return user_list


    @staticmethod
    def search_user(auth, query: str, offset: str = '0', num: str = '25', douyin_user_fans="", douyin_user_type="", **kwargs):
        """
        搜索用户.
        :param auth: DouyinAuth object.
        :param query:  搜索关键字.
        :param offset:  搜索结果偏移量.
        :param num:  搜索结果数量.
        :param douyin_user_fans: 粉丝数量 空字符串 (0_1k 1000以下) (1k_1w 1000-10000) (1w_10w 10000-100000) (10w_100w 10w-100w粉丝) (100w_ 100w以上)
        :param douyin_user_type: 用户类型 空字符串 不限 common_user 普通用户 enterprise_user 企业用户 personal_user 个人认证用户
        :return: JSON数据.
        """
        # 结尾斜杠不能少，浏览器实测就是 /search/
        api = "/aweme/v1/web/discover/search/"
        headers = HeaderBuilder().build(HeaderType.GET)
        refer = f'https://www.douyin.com/search/{urllib.parse.quote(query)}?type=user'
        headers.set_referer(refer)
        uifid = auth.cookie.get('UIFID', '')
        if uifid:
            headers.set_header("uifid", uifid)
        has_filter = bool(douyin_user_fans or douyin_user_type)
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("search_channel", 'aweme_user_web')
        if has_filter:
            params.add_param("search_filter_value",
                             r'{"douyin_user_fans":["%s"],"douyin_user_type":["%s"]}'
                             % (douyin_user_fans, douyin_user_type))
        params.add_param("keyword", query)
        params.add_param("search_source", 'normal_search')
        params.add_param("query_correct_type", '1')
        params.add_param("is_filter_search", '1' if has_filter else '0')
        params.add_param("from_group_id", '')
        params.add_param("disable_rs", '0')
        params.add_param("offset", offset)
        params.add_param("count", num)
        params.add_param("need_filter_settings", '1' if offset == '0' else '0')
        params.add_param("list_type", 'single')
        params.add_param("pc_search_top_1_params", '{"enable_ai_search_top_1":1}')
        params.add_param("update_version_code", '170400')
        params.add_param("pc_client_type", '1')
        params.add_param("pc_libra_divert", 'Windows')
        params.add_param("support_h265", '1')
        params.add_param("support_dash", '1')
        params.add_param("cpu_core_num", get_profile()["cpu_core_num"])
        params.add_param("version_code", '170400')
        params.add_param("version_name", '17.4.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", get_profile()["screen_width"])
        params.add_param("screen_height", get_profile()["screen_height"])
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", get_profile()["browser_name"])
        params.add_param("browser_version", get_profile()["browser_version"])
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", get_profile()["engine_version"])
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("device_memory", get_profile()["device_memory"])
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        params.add_param("round_trip_time", '50')
        params.with_web_id(auth, refer)
        if uifid:
            params.add_param("uifid", uifid)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        # 搜索接口的 verifyFp / fp 在 a_bogus 之后，与评论接口相反
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        check_risk_response(resp)
        return resp.json()

    @staticmethod
    def search_live(auth, query: str, offset: str = '0', num: str = '15', **kwargs):
        """
        搜索直播.
        :param auth: DouyinAuth object.
        :param query:  搜索关键字.
        :param offset:  搜索结果偏移量.
        :param num:  搜索数量.
        :return: JSON数据.
        """
        api = "/aweme/v1/web/live/search/"
        headers = HeaderBuilder().build(HeaderType.GET)
        refer = f'https://www.douyin.com/search/{urllib.parse.quote(query)}?aid={uuid.uuid4()}&type=live'
        headers.set_referer(refer)
        headers.with_uifid(auth)
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("search_channel", 'aweme_live')
        params.add_param("keyword", query)
        params.add_param("search_source", 'normal_search')
        params.add_param("query_correct_type", '1')
        params.add_param("is_filter_search", '0')
        params.add_param("from_group_id", '')
        params.add_param("disable_rs", '0')
        params.add_param("offset", offset)
        params.add_param("count", num)
        params.add_param("need_filter_settings", '1' if offset == '0' else '0')
        params.add_param("list_type", 'single')
        # 实录：list_type 之后是 pc_search_top_1_params（空值），再进公共组
        params.add_param("pc_search_top_1_params", '{"enable_ai_search_top_1":1}')
        params.with_platform(round_trip_time='0')
        params.with_web_id(auth, refer)
        params.with_uifid(auth)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        # 实录里 verifyFp / fp 在 a_bogus 之后
        params.with_verify_fp(auth)
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        check_risk_response(resp)
        return resp.json()

    @staticmethod
    def search_some_live(auth, query: str, num: int, **kwargs) -> list:
        """
        搜索指定数量直播.
        :param auth: DouyinAuth object.
        :param query:  搜索关键字.
        :param num:  搜索数量.
        :return: 直播列表.
        """
        offset = "0"
        count = "15"
        live_list = []
        while True:
            res_json = DouyinAPI.search_live(auth, query, offset, count)
            lives = res_json["data"]
            live_list.extend(lives)
            if res_json["has_more"] != 1 or len(live_list) >= num:
                break
            offset = str(int(offset) + int(count))
        if len(live_list) > num:
            live_list = live_list[:num]
        return live_list

    @staticmethod
    def get_user_favorite(auth, sec_id: str, max_cursor: str = '0', num: str = '18', **kwargs):
        """
        获取用户收藏.
        :param auth: DouyinAuth object.
        :param sec_id:  用户SECID.
        :param max_cursor:  翻页游标.
        :param num: 要获取的收藏数量.
        :return: JSON.
        """
        headers = HeaderBuilder.build(HeaderType.GET)
        refer = f"https://www.douyin.com/user/{sec_id}?showTab=like"
        headers.set_referer(refer)
        headers.with_uifid(auth)
        # 实录 headers_wire 里这个接口带 bd-ticket-guard 全套
        headers.with_bd_readonly(auth)
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        # 以前这里写死了别人的 sec_user_id，收藏页取的根本不是入参那个用户
        params.add_param("sec_user_id", sec_id)
        params.add_param("max_cursor", max_cursor)
        params.add_param("min_cursor", '0')
        # whale_cut_token 是空值字段，浏览器确实发（`whale_cut_token=`）
        params.add_param("whale_cut_token", '')
        params.add_param("cut_version", '1')
        params.add_param("count", num)
        params.add_param("publish_video_strategy_type", '2')
        # 公共组换 with_platform()：手写那版缺 pc_libra_divert / support_h265 / support_dash
        params.with_platform(round_trip_time='0')
        params.with_web_id(auth=auth, url=refer)
        params.with_uifid(auth)
        params.with_verify_fp(auth)
        # 实录里这个接口 **不带 msToken**（a_bogus 之后直接是 timestamp）
        params.with_a_bogus()
        response = requests.get(
            params.signed_url('https://www.douyin.com/aweme/v1/web/aweme/favorite/', auth),
            headers=headers.get(), cookies=auth.cookie, verify=False)
        check_risk_response(response)
        return response.json()


    @staticmethod
    def get_my_uid(auth, **kwargs) -> int:
        """
        获取自己的用户ID.
        :param auth: DouyinAuth object.
        :return: 用户ID.
        """
        url = 'https://www.douyin.com/aweme/v1/web/query/user/'
        headers = HeaderBuilder().build(HeaderType.GET)
        refer = 'https://www.douyin.com/'
        headers.set_header('referer', refer)
        headers.with_uifid(auth)
        params = Params()
        params.add_param('publish_video_strategy_type', '2')
        params.with_platform()
        params.with_uifid(auth)
        params.with_web_id(auth, refer)
        params.add_param('verifyFp', auth.cookie['s_v_web_id'])
        params.add_param('fp', auth.cookie['s_v_web_id'])
        params.with_a_bogus()
        resp = requests.get(url, params=params.get(), verify=False, headers=headers.get(), cookies=auth.cookie)
        check_risk_response(resp)
        resp_json = resp.json()
        return int(resp_json['user_uid'])

    @staticmethod
    def get_my_sec_uid(auth, **kwargs) -> str:
        """
        获取自己的SECID.

        主站 `/user/self` 已改成客户端渲染，HTML 里不再有 secUid（2026-08-16 复核），
        所以走创作者中心的 user/info 拿（同一套 cookie），HTML 仅作兜底。
        :param auth: DouyinAuth object.
        :return: SECID.
        """
        try:
            resp = requests.get(
                "https://creator.douyin.com/web/api/media/user/info/",
                headers={
                    "accept": "application/json, text/plain, */*",
                    "accept-language": HeaderBuilder.accept_language,
                    "referer": "https://creator.douyin.com/creator-micro/home",
                    "user-agent": HeaderBuilder.ua,
                },
                cookies=auth.cookie, verify=False, timeout=20,
            )
            sec_uid = ((resp.json() or {}).get("user") or {}).get("sec_uid")
            if sec_uid:
                return sec_uid
        except Exception:
            pass

        headers = HeaderBuilder().build(HeaderType.GET)
        response = requests.get("https://www.douyin.com/user/self", headers=headers.get(),
                                cookies=auth.cookie, params={"from_tab_name": "main"})
        found = re.findall(r'\\"secUid\\":\\"(.*?)\\"', response.text)
        if not found:
            raise RuntimeError("未取到 sec_uid：创作者接口与主站 HTML 都没拿到，请检查登录态")
        return found[0]


    @staticmethod
    def get_live_info(auth_, live_id, **kwargs):
        """
        获取直播间信息.
        :param live_id: 直播间ID
        :return: 直播间ID, 用户ID, ttwid
        """
        url = "https://live.douyin.com/" + live_id
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,en;q=0.7,ja;q=0.6",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=0, i",
            "referer": "https://live.douyin.com/?from_nav=1",
            "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Google Chrome\";v=\"138\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "upgrade-insecure-requests": "1",
            "user-agent": get_profile()["ua"]
        }
        # Use the same persistent Auth transport as the main-site calls.  The
        # live landing page may rotate ``ttwid``; absorbing that Set-Cookie is
        # required before the following REST/WebSocket handshake.  Older code
        # indexed the response cookie directly and crashed when an edge did
        # not rotate it on every visit.
        if hasattr(auth_, "request"):
            res = auth_.request(
                "GET", url, headers=headers, verify=False,
                timeout=kwargs.get("timeout", 30),
            )
            try:
                from utils.passport import merge_set_cookies
                merge_set_cookies(auth_, res.cookies.get_dict())
            except Exception:
                pass
        else:
            res = requests.get(url, headers=headers, cookies=auth_.cookie,
                               verify=False)
        ttwid = (res.cookies.get_dict().get("ttwid")
                 or (getattr(auth_, "cookie", {}) or {}).get("ttwid", ""))
        soup = BeautifulSoup(res.text, 'html.parser')
        scripts = soup.select('script[nonce]')
        # print(res.text)
        for script in scripts:
            if script.string is not None and 'roomId' in script.string:
                try:
                    user_id = re.findall(r'\\"user_unique_id\\":\\"(\d+)\\"', script.string)[0]
                    room_id = re.findall(r'\\"roomId\\":\\"(\d+)\\"', script.string)[0]
                    user_unique_id = re.findall(r'\\"user_unique_id\\":\\"(\d+)\\"', script.string)[0]
                    room_info = re.findall(r'\\"roomInfo\\":\{\\"room\\":\{\\"id_str\\":\\".*?\\",\\"status\\":(.*?),\\"status_str\\":\\".*?\\",\\"title\\":\\"(.*?)\\"', script.string)[0]
                    # "anchor\":{\"id_str\":\"3998258005032616\",\
                    anchor_id = re.findall(r'\\"anchor\\":\{\\"id_str\\":\\"(\d+)\\"', script.string)[0]
                    # , \"sec_uid\":\"M
                    sec_uid = re.findall(r'\\"sec_uid\\":\\"(.*?)\\"', script.string)[0]
                    room_status = room_info[0]
                    room_title = room_info[1]
                    res = {
                        "room_id": room_id,
                        "user_id": user_id,
                        "user_unique_id": user_unique_id,
                        "anchor_id": anchor_id,
                        "sec_uid": sec_uid,
                        "ttwid": ttwid,
                        # 2 是直播中 4 是未开播
                        "room_status": room_status,
                        "room_title": room_title
                    }
                    # A parsed room page is the first concrete live-REST
                    # verification point.  Construction of a shared Auth
                    # alone does not imply this flag.
                    if hasattr(auth_, "live_rest_verified"):
                        auth_.live_rest_verified = True
                    return res
                except Exception:
                    pass
        # Some live edges return a server-rendered JSON blob without a
        # ``nonce`` attribute.  Keep the parser useful for those responses by
        # scanning the complete document as a final, read-only fallback.
        text = res.text or ""
        if "roomId" in text:
            try:
                def _first(pattern):
                    match = re.search(pattern, text)
                    return match.group(1) if match else ""
                room_id = _first(r'\\"roomId\\"\s*:\s*\\"(\d+)\\"')
                user_id = _first(r'\\"user_unique_id\\"\s*:\s*\\"(\d+)\\"')
                anchor_id = _first(r'\\"anchor\\"\s*:\s*\\{[^{}]*?\\"id_str\\"\s*:\s*\\"(\d+)\\"')
                sec_uid = _first(r'\\"sec_uid\\"\s*:\s*\\"([^\"]+)\\"')
                if room_id and user_id:
                    if hasattr(auth_, "live_rest_verified"):
                        auth_.live_rest_verified = True
                    return {
                        "room_id": room_id,
                        "user_id": user_id,
                        "user_unique_id": user_id,
                        "anchor_id": anchor_id or user_id,
                        "sec_uid": sec_uid,
                        "ttwid": ttwid,
                    }
            except Exception:
                pass
        return None

    @staticmethod
    def _live_ecom_headers(url):
        """live.douyin.com 上电商接口的请求头。

        实录（2026-08-17 `/live/promotions/pop/v3/` 的 wire dump）里只有
        `uifid` / `referer` / `user-agent` / `accept` 四个业务头，
        **不发 `sec-ch-ua` 三兄弟** —— 这点和主站 aweme XHR 相反（那边要发），
        和 creator 域一致。
        """
        headers = HeaderBuilder.build(HeaderType.GET)
        headers.set_referer(url)
        for key in ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"):
            headers.remove_header(key)
        return headers

    @staticmethod
    def get_live_production(auth, url: str, room_id: str, author_id: str, offset: str = '0',
                            ecom_scene_id: str = '1001', **kwargs):
        """
        获取直播间正在讲解的商品（小黄车弹窗卡）。
        :param auth: DouyinAuth object.
        :param url: 直播间链接.
        :param room_id: 直播间ID
        :param author_id: 主播ID
        :param offset: 兼容旧签名，本端点一次给全，不分页（忽略）。
        :return: JSON，`promotions` 是商品列表，每项含 promotion_id / product_id /
            title / min_price / max_price（单位：分）/ cover / detail_url / shop_id /
            status / in_stock 等。

        2026-08-17 换端点的原因（拿真带货直播间实测，room 7674681830785321762）：
        原实现打的 `/live/promotions/page/`（「全部商品」面板）在服务端已经坏了，
        判据是**真实浏览器**发同样的请求也是 HTTP 200 + 空 body，页面上直接显示
        「服务异常，重新刷新试试」；`/live/promotions/page/top/` 则返回
        `status_code=100111 系统开小差了`。与登录态无关，也与电商授权无关
        （`getUserAuth` 已确认 `auth_flag=1` 仍然是空）。
        当前 PC 直播间真正在用、且能拿到数据的是这个 `pop/v3`。
        """
        api = "/live/promotions/pop/v3/"
        headers = DouyinAPI._live_ecom_headers(url)
        headers.with_uifid(auth)
        # entrance_info 是 JSON 串且**发出去时要整体 URL 编码**（实录如此）
        entrance_info = json.dumps({
            "room_id": room_id,
            "anchor_id": author_id,
            "carrier_type": "live_popup_card",
            "ecom_scene_id": ecom_scene_id,
        }, separators=(",", ":"))
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("room_id", room_id)
        params.add_param("author_id", author_id)
        params.add_param("live_scene_id", "0")
        params.add_param("entrance_info", urllib.parse.quote(entrance_info, safe=""))
        params.with_live_platform()
        params.with_web_id(auth, url)
        params.with_uifid(auth)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus(host=LIVE_HOST)
        res = requests.get(f'{DouyinAPI.live_url}{api}', headers=headers.get(), cookies=auth.cookie,
                           params=params.get(), verify=False)
        if not res.content:
            # 该房间没有挂商品时也是空响应，不能当签名错误
            logger.info(f"直播间商品接口返回空响应（多为该直播间未挂商品），room_id={room_id}")
            return {"promotions": []}
        check_risk_response(res)
        return res.json()

    @staticmethod
    def get_all_live_production(auth, url: str, **kwargs):
        """
        获取直播间的商品列表.
        :param auth: DouyinAuth object.
        :param url: 直播间链接.
        :return: 商品列表（list）。

        `pop/v3` 一次返回整个轮播列表，没有游标，所以这里不再翻页。
        「全部商品」那个分页端点已经服务端不可用，见 `get_live_production`。
        """
        room_info = DouyinAPI.get_live_info(auth, url.split("/")[-1].split("?")[0])
        if not room_info:
            raise RuntimeError(f"未能解析直播间信息: {url}")
        room_id = room_info["room_id"]
        # get_live_info 返回的主播 ID 字段名是 anchor_id
        author_id = room_info["anchor_id"]
        res_json = DouyinAPI.get_live_production(auth, url, room_id, author_id)
        return res_json.get("promotions") or []

    @staticmethod
    def get_live_production_detail(auth, url, promotion_id, origin_type: str = '638303', **kwargs):
        """
        获取商品详情（详情图 / 规格 / 详情页跳转链接）。
        :param auth: DouyinAuth object.
        :param url: 来源页链接（直播间链接即可，作 referer）。
        :param promotion_id: 商品ID，取 `get_live_production` 返回的 `promotion_id`。
        :param origin_type: 来源标识，直播间取 `638303`（商品 `detail_url` 里带的就是它）。
        :return: JSON，`detail_info` 含 detail_imgs / detail_imgs_new / title_image /
            product_format / jump_url。

        2026-08-17 换端点：原实现打 `/ecom/product/detail/saas/pc/`，实测恒返回
        `status_code=0` 但 `promotions: null`（三种 origin_type 都试过），
        和「全部商品」面板一起坏在服务端。前端 bundle 里同一模块还有
        `/aweme/v2/shop/promotion/pack/detail/`，这条是活的。
        参数形状照前端原文：query 只有 `is_h5` + `origin_type`，其余进 body。
        """
        api = "/aweme/v2/shop/promotion/pack/detail/"
        headers = HeaderBuilder.build(HeaderType.FORM)
        headers.set_header("origin", DouyinAPI.live_url)
        headers.set_referer(url)
        headers.with_csrf(auth.cookie_str)
        headers.with_uifid(auth)
        for key in ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"):
            headers.remove_header(key)
        params = Params()
        params.add_param("is_h5", "1")
        params.add_param("origin_type", origin_type)
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.with_live_platform()
        params.with_web_id(auth, url)
        params.with_uifid(auth)
        params.add_param("msToken", auth.msToken)
        data = {
            "is_h5": "1",
            "bff_type": "2",
            "origin_type": origin_type,
            "promotion_id": promotion_id,
        }
        params.with_a_bogus(data, host=LIVE_HOST)
        res = requests.post(f'{DouyinAPI.live_url}{api}', headers=headers.get(), params=params.get(),
                            cookies=auth.cookie, data=data, verify=False)
        check_risk_response(res)
        return res.json()

    @staticmethod
    def get_product_comments(auth, product_id: str, shop_id: str, cursor: str = '0',
                             count: str = '10', sort_type: str = '0', tag_id: str = '',
                             stat_id: str = '', **kwargs):
        """
        获取商品评价.
        :param auth: DouyinAuth object.
        :param product_id: 商品ID（= `get_live_production` 里的 product_id）。
        :param shop_id: 店铺ID，同一条商品数据里的 `shop_id`。
        :param cursor: 翻页游标.
        :param count: 每页条数.
        :return: JSON，`data.Comments` / `data.Count` / `data.HasMore`（注意是大写驼峰）。
        """
        api = "/aweme/v1/web/ecom/product/comments/"
        refer = f"{DouyinAPI.douyin_url}/"
        headers = HeaderBuilder.build(HeaderType.GET)
        headers.set_referer(refer)
        headers.with_uifid(auth)
        params = Params()
        params.add_param("product_id", product_id)
        params.add_param("shop_id", shop_id)
        params.add_param("cursor", cursor)
        params.add_param("count", count)
        params.add_param("stat_id", stat_id)
        params.add_param("tag_id", tag_id)
        params.add_param("sort_type", sort_type)
        params.with_platform(round_trip_time='0', auth=auth, url=refer)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        res = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(),
                           cookies=auth.cookie, params=params.get(), verify=False)
        check_risk_response(res)
        return res.json()

    @staticmethod
    def get_product_comment_counter(auth, product_id: str, shop_id: str, stat_id: str = '',
                                    **kwargs):
        """
        获取商品评价的分类计数（好评 / 差评 / 带图等标签）。
        :return: JSON，`counter_info`。
        """
        api = "/aweme/v1/web/ecom/product/comment/counter/"
        refer = f"{DouyinAPI.douyin_url}/"
        headers = HeaderBuilder.build(HeaderType.GET)
        headers.set_referer(refer)
        headers.with_uifid(auth)
        params = Params()
        params.add_param("product_id", product_id)
        params.add_param("shop_id", shop_id)
        params.add_param("stat_id", stat_id)
        params.with_platform(round_trip_time='0', auth=auth, url=refer)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        res = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(),
                           cookies=auth.cookie, params=params.get(), verify=False)
        check_risk_response(res)
        return res.json()

    @staticmethod
    def collect_aweme(auth, aweme_id: str, action: str = '1', **kwargs):
        """
        收藏或取消收藏视频.
        :param auth: DouyinAuth object.
        :param aweme_id: 视频ID.
        :param action: 1: 收藏, 0: 取消收藏.
        :return: 响应JSON.
        """
        api = '/aweme/v1/web/aweme/collect/'
        headers = HeaderBuilder().build(HeaderType.FORM)
        refer = "https://www.douyin.com/?recommend=1"
        headers.set_referer(refer)
        headers.with_bd_readonly(auth)
        # 注意：实录里 collect 接口**没有** x-tt-session-dtrait（digg 才有）
        headers.with_csrf(auth.cookie_str)
        headers.with_uifid(auth)
        headers.set_header("origin", DouyinAPI.douyin_url)
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("pc_client_type", "1")
        params.with_platform(round_trip_time='0')
        params.with_web_id(auth, refer)
        params.with_uifid(auth)
        params.with_verify_fp(auth)
        params.add_param("msToken", auth.msToken)
        data = {
            "action": action,
            "aweme_id": aweme_id,
            "aweme_type": "0",
        }
        params.with_a_bogus(data)
        # 实录 query 末尾还有 uid = md5(登录用户数字 ID)，不参与签名
        params.add_param("uid", DouyinAPI._comment_uid(auth))
        res = requests.post(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), params=params.get(),
                            cookies=auth.cookie, data=data, verify=False)
        check_risk_response(res)
        return res.json()

    @staticmethod
    def move_collect_aweme(auth, aweme_id: str, collect_name: str, collect_id: str, **kwargs):
        """
        移动视频到指定收藏夹（需要先收藏视频）
        :param collect_name: 收藏夹名称
        :param collect_id: 收藏夹ID
        :param auth: DouyinAuth object.
        :param aweme_id: 视频ID.
        :return: 响应JSON.
        """
        api = '/aweme/v1/web/collects/video/move/'
        headers = HeaderBuilder().build(HeaderType.FORM)
        refer = "https://www.douyin.com/?recommend=1"
        headers.set_referer(refer)
        headers.with_bd_readonly(auth)
        # 实录 digg 带 x-tt-session-dtrait（写接口的风控头）
        _dt = auth.session_dtrait_header(api)
        if _dt:
            headers.set_header('x-tt-session-dtrait', _dt)
        headers.with_csrf(auth.cookie_str)
        headers.with_uifid(auth)
        headers.set_header("origin", DouyinAPI.douyin_url)
        params = Params()
        params.add_param("aid", "6383")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_name", get_profile()["browser_name"])
        params.add_param("browser_online", "true")
        params.add_param("browser_platform", get_profile()["platform"])
        params.add_param("browser_version", get_profile()["browser_version"])
        params.add_param("channel", "channel_pc_web")
        params.add_param("collects_name", collect_name)
        params.add_param("cookie_enabled", "true")
        params.add_param("cpu_core_num", get_profile()["cpu_core_num"])
        params.add_param("device_memory", get_profile()["device_memory"])
        params.add_param("device_platform", "webapp")
        params.add_param("downlink", "10")
        params.add_param("effective_type", "4g")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", get_profile()["engine_version"])
        params.add_param("item_ids", aweme_id)
        params.add_param("item_type", "2")
        params.add_param("move_collects_list", collect_id)
        params.add_param("os_name", "Windows")
        params.add_param("os_version", get_profile()["os_version"])
        params.add_param("pc_client_type", "1")
        params.add_param("platform", "PC")
        params.add_param("round_trip_time", "50")
        params.add_param("screen_height", get_profile()["screen_height"])
        params.add_param("screen_width", get_profile()["screen_width"])
        params.add_param("to_collects_id", collect_id)
        params.add_param("update_collects_sort", "true")
        params.add_param("update_version_code", "170400")
        params.add_param("version_code", "170400")
        params.add_param("version_name", "17.4.0")
        params.with_web_id(auth, refer)
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        res = requests.post(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), params=params.get(),
                            cookies=auth.cookie, verify=False)
        check_risk_response(res)
        return res.json()

    @staticmethod
    def remove_collect_aweme(auth, aweme_id: str, collect_name: str, collect_id: str, **kwargs):
        """
        从指定收藏夹中移除视频（需要先收藏视频）
        :param collect_name: 收藏夹名称
        :param collect_id: 收藏夹ID
        :param auth: DouyinAuth object.
        :param aweme_id: 视频ID.
        :return: 响应JSON.
        """
        api = '/aweme/v1/web/collects/video/move/'
        headers = HeaderBuilder().build(HeaderType.FORM)
        refer = "https://www.douyin.com/user/self?showTab=favorite_collection"
        headers.set_referer(refer)
        headers.with_bd_readonly(auth)
        headers.with_csrf(auth.cookie_str)
        headers.with_uifid(auth)
        headers.set_header("origin", DouyinAPI.douyin_url)
        params = Params()
        params.add_param("aid", "6383")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_name", get_profile()["browser_name"])
        params.add_param("browser_online", "true")
        params.add_param("browser_platform", get_profile()["platform"])
        params.add_param("browser_version", get_profile()["browser_version"])
        params.add_param("channel", "channel_pc_web")
        params.add_param("collects_name", collect_name)
        params.add_param("cookie_enabled", "true")
        params.add_param("cpu_core_num", get_profile()["cpu_core_num"])
        params.add_param("device_memory", get_profile()["device_memory"])
        params.add_param("device_platform", "webapp")
        params.add_param("downlink", "10")
        params.add_param("effective_type", "4g")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", get_profile()["engine_version"])
        params.add_param("from_collects_id", collect_id)
        params.add_param("item_ids", aweme_id)
        params.add_param("item_type", "2")
        params.add_param("os_name", "Windows")
        params.add_param("os_version", get_profile()["os_version"])
        params.add_param("pc_client_type", "1")
        params.add_param("platform", "PC")
        params.add_param("round_trip_time", "50")
        params.add_param("screen_height", get_profile()["screen_height"])
        params.add_param("screen_width", get_profile()["screen_width"])
        params.add_param("update_version_code", "170400")
        params.add_param("version_code", "170400")
        params.add_param("version_name", "17.4.0")
        params.with_web_id(auth, refer)
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        res = requests.post(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), params=params.get(),
                            cookies=auth.cookie, verify=False)
        check_risk_response(res)
        return res.json()

    @staticmethod
    def get_collect_list(auth, **kwargs):
        """
        获取我的收藏夹列表
        :param auth: DouyinAuth object.
        :return: JSON.
        """
        api = "/aweme/v1/web/collects/list/"
        headers = HeaderBuilder().build(HeaderType.GET)
        headers.with_uifid(auth)
        refer = "https://www.douyin.com/?recommend=1"
        headers.set_referer(refer)
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("cursor", "0")
        params.add_param("count", "20")
        # 公共组换 with_platform()：手写那版缺 pc_libra_divert / support_h265 / support_dash，
        # 且 downlink 写死 5.95、round_trip_time 写死 200（实录是 10 / 0）
        params.with_platform(round_trip_time='0')
        params.with_web_id(auth, refer)
        params.with_uifid(auth)
        params.with_verify_fp(auth)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        res = requests.get(params.signed_url(f'{DouyinAPI.douyin_url}{api}', auth),
                           headers=headers.get(),
                           cookies=auth.cookie, verify=False)
        check_risk_response(res)
        return res.json()

    @staticmethod
    def get_user_follower_list(auth, user_id: str, sec_id: str, max_time: str = None, count: str = '20', **kwargs):
        """
        获取用户的粉丝列表
        :param auth: DouyinAuth object.
        :param user_id: 用户ID.
        :param sec_id: 用户sec_id.
        :param max_time: 最大时间戳.
        :param count: 数量.
        :return:  JSON.
        """
        # 实录 curl：max_time 传**当前秒级时间戳**、source_type=1 才返回粉丝；
        # 传 max_time=0 时服务端走另一条分支，返回 followers=[]（total 也是 0）
        if not max_time or max_time == '0':
            max_time = str(int(time.time()))
        # 实录 curl：max_time 传当前秒级时间戳、source_type=1 才返回粉丝；
        # 传 0 服务端走另一分支返回空列表（status_code 仍是 0，别被骗）
        if not max_time or max_time == '0':
            max_time = str(int(time.time()))
        api = "/aweme/v1/web/user/follower/list/"
        headers = HeaderBuilder().build(HeaderType.GET)
        headers.with_uifid(auth)
        refer = f"https://www.douyin.com/user/{sec_id}"
        headers.set_referer(refer)
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("user_id", user_id)
        params.add_param("sec_user_id", sec_id)
        params.add_param("offset", '0')
        params.add_param("min_time", '0')
        params.add_param("max_time", max_time)
        params.add_param("count", count)
        params.add_param("source_type", '2' if max_time == '0' else '1')
        params.add_param("gps_access", '0')
        params.add_param("address_book_access", '0')
        params.with_platform(round_trip_time='0')
        params.with_web_id(auth, refer)
        params.with_uifid(auth)
        params.with_verify_fp(auth)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        res = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), params=params.get(),
                           cookies=auth.cookie, verify=False)
        check_risk_response(res)
        return res.json()

    @staticmethod
    def get_some_user_follower_list(auth, user_id: str, sec_id: str, num: int, **kwargs) -> list:
        """
        获取用户的前num个粉丝列表
        :param auth: DouyinAuth object.
        :param user_id: 用户ID.
        :param sec_id: 用户sec_id.
        :param num: 要获取的数量
        :return: 粉丝列表.
        """
        max_time = "0"
        count = "20"
        follower_list = []
        while True:
            res_json = DouyinAPI.get_user_follower_list(auth, user_id, sec_id, max_time, count)
            # 用户隐私受限（status_code=2096）时 followers 为 null 且无 has_more 字段，防空值崩溃
            followers = res_json["followers"] or []
            follower_list.extend(followers)
            if res_json.get("has_more") != 1 or len(follower_list) >= num:
                break
            max_time = res_json["min_time"]
        if len(follower_list) > num:
            follower_list = follower_list[:num]
        return follower_list

    @staticmethod
    def get_user_following_list(auth, user_id: str, sec_id: str, max_time: str = None, count: str = '20', **kwargs):
        """
        获取用户的关注列表
        :param auth: DouyinAuth object.
        :param user_id: 用户ID.
        :param sec_id: 用户sec_id.
        :param max_time: 最大时间戳.
        :param count: 数量.
        :return:
        """
        # 同 follower/list：max_time 传**当前秒级时间戳**、source_type=1 才返回 followings；
        # 传 max_time=0 时服务端走推荐分支，返回 followings=[]（total 也是 0，status_code 仍是 0，别被骗）
        if not max_time or max_time == '0':
            max_time = str(int(time.time()))
        api = "/aweme/v1/web/user/following/list/"
        headers = HeaderBuilder().build(HeaderType.GET)
        refer = f"https://www.douyin.com/user/{sec_id}"
        headers.set_referer(refer)
        # 实录 headers_wire 里带 bd-ticket-guard 全套
        headers.with_bd_readonly(auth)
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("user_id", user_id)
        params.add_param("sec_user_id", sec_id)
        params.add_param("offset", '0')
        params.add_param("min_time", '0')
        params.add_param("max_time", max_time)
        params.add_param("count", count)
        params.add_param("source_type", '2' if max_time == '0' else '1')
        params.add_param("gps_access", '0')
        params.add_param("address_book_access", '0')
        params.add_param("is_top", '1')
        params.add_param("pc_client_type", '1')
        # 实录里这个接口特有两个 webcast 字段，位置在 pc_client_type 之后
        params.add_param("pc_libra_divert", 'Windows')
        params.add_param("support_h265", '1')
        params.add_param("support_dash", '1')
        params.add_param("webcast_sdk_version", '170400')
        params.add_param("webcast_version_code", '170400')
        params.add_param("version_code", '170400')
        params.add_param("version_name", '17.4.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", get_profile()["screen_width"])
        params.add_param("screen_height", get_profile()["screen_height"])
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", get_profile()["browser_name"])
        params.add_param("browser_version", get_profile()["browser_version"])
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", get_profile()["engine_version"])
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("cpu_core_num", get_profile()["cpu_core_num"])
        params.add_param("device_memory", get_profile()["device_memory"])
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        params.add_param("round_trip_time", '0')
        params.with_web_id(auth, refer)
        params.with_verify_fp(auth)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        # collects/list 在 secsdk webSign 策略表里，缺签名会被 ArgusSecurityPlugin 403
        res = requests.get(params.signed_url(f'{DouyinAPI.douyin_url}{api}', auth),
                           headers=headers.get(),
                           cookies=auth.cookie, verify=False)
        check_risk_response(res)
        return res.json()

    @staticmethod
    def get_some_user_following_list(auth, user_id: str, sec_id: str, num: int, **kwargs) -> list:
        """
        获取用户的前num个关注列表
        :param auth: DouyinAuth object.
        :param user_id: 用户ID.
        :param sec_id: 用户sec_id.
        :param num: 要获取的数量
        :return: 关注列表.
        """
        max_time = "0"
        count = "20"
        following_list = []
        while True:
            res_json = DouyinAPI.get_user_following_list(auth, user_id, sec_id, max_time, count)
            # 用户隐私受限（status_code=2096）时 followings 为 null 且无 has_more 字段，防空值崩溃
            followings = res_json["followings"] or []
            following_list.extend(followings)
            if res_json.get("has_more") != 1 or len(following_list) >= num:
                break
            max_time = res_json["min_time"]
        if len(following_list) > num:
            following_list = following_list[:num]
        return following_list

    @staticmethod
    def get_notice_list(auth, min_time='0', max_time='0', count='10', notice_group='960', **kwargs):
        """
        获得通知
        :param auth: DouyinAuth object.
        :param min_time: 最小时间戳.
        :param max_time: 最大时间戳.
        :param count: 数量.
        :param notice_group: 消息类型 700 全部消息 401 粉丝 601 @我的 2 评论 3 点赞 520 弹幕
        :return: JSON.
        """
        api = "/aweme/v1/web/notice/"
        headers = HeaderBuilder().build(HeaderType.GET)
        headers.with_uifid(auth)
        refer = "https://www.douyin.com/?recommend=1"
        headers.set_referer(refer)
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("is_new_notice", '1')
        params.add_param("is_mark_read", '1')
        params.add_param("notice_group", notice_group)
        params.add_param("count", count)
        params.add_param("min_time", min_time)
        params.add_param("max_time", max_time)
        params.with_platform(round_trip_time='0')
        params.with_web_id(auth, refer)
        params.with_uifid(auth)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        res = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), params=params.get(),
                           cookies=auth.cookie, verify=False)
        check_risk_response(res)
        res_json = res.json()
        # 服务端把通知放在 notice_list_v2；旧的 notice_list 恒为 []。
        # 只看 status_code 会以为正常（sc=0），实际一条数据都没取到。
        # 这里回填一份到 notice_list，保证两个字段都能用。
        if not res_json.get("notice_list") and res_json.get("notice_list_v2"):
            res_json["notice_list"] = res_json["notice_list_v2"]
        return res_json

    @staticmethod
    def get_some_notice_list(auth, num: int = 20, notice_group='960', **kwargs) -> list:
        """
        获得前num条通知
        :param auth: DouyinAuth object.
        :param num: 数量.
        :param notice_group: 消息类型 | 700 全部消息 401 粉丝 601 @我的 2 评论 3 点赞 520 弹幕
        :return:
        """
        min_time = "0"
        max_time = "0"
        count = "10"
        notice_list = []
        while True:
            res_json = DouyinAPI.get_notice_list(auth, min_time, max_time, count, notice_group)
            notices = res_json["notice_list_v2"]
            notice_list.extend(notices)
            if res_json["has_more"] != 1 or len(notice_list) >= num:
                break
            min_time = res_json["min_time"]
            max_time = res_json["max_time"]
        if len(notice_list) > num:
            notice_list = notice_list[:num]
        return notice_list

    @staticmethod
    def get_feed(auth, count='20', refresh_index='2', **kwargs):
        """
        获取首页推荐视频
        :param auth: DouyinAuth object.
        :param count: 数量.
        :param refresh_index: 刷新索引.
        :return: JSON.
        """
        api = "/aweme/v1/web/module/feed/"
        headers = HeaderBuilder().build(HeaderType.GET)
        refer = "https://www.douyin.com/"
        headers.set_referer(refer)
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("module_id", '3003101')
        params.add_param("count", count)
        params.add_param("filterGids", '')
        params.add_param("presented_ids", '')
        params.add_param("refresh_index", refresh_index)
        params.add_param("refer_id", '')
        params.add_param("refer_type", '10')
        params.add_param("awemePcRecRawData", '{"is_client":false}')
        params.add_param("Seo-Flag", '0')
        params.add_param("install_time", '1715480185')
        params.add_param("pc_client_type", '1')
        params.add_param("update_version_code", '170400')
        params.add_param("version_code", '170400')
        params.add_param("version_name", '17.4.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", get_profile()["screen_width"])
        params.add_param("screen_height", get_profile()["screen_height"])
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", get_profile()["browser_name"])
        params.add_param("browser_version", get_profile()["browser_version"])
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", get_profile()["engine_version"])
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("cpu_core_num", get_profile()["cpu_core_num"])
        params.add_param("device_memory", get_profile()["device_memory"])
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        params.add_param("round_trip_time", '100')
        params.with_web_id(auth, refer)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])

        res = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), params=params.get(),
                           cookies=auth.cookie, verify=False)
        check_risk_response(res)
        return res.json()



    @staticmethod
    def get_rank_list(auth, room_id: str, anchor_id: str, sec_anchor_id: str):
        headers = HeaderBuilder().build(HeaderType.GET)
        refer = "https://live.douyin.com"
        headers.set_referer(refer)
        url = "https://live.douyin.com/webcast/ranklist/audience/"
        params = Params()

        # params = {
        #     "aid": "6383",
        #     "app_name": "douyin_web",
        #     "live_id": "1",
        #     "device_platform": "web",
        #     "language": "zh-CN",
        #     "enter_from": "web_live",
        #     "cookie_enabled": "true",
        #     "screen_width": "2560",
        #     "screen_height": "1600",
        #     "browser_language": "zh-CN",
        #     "browser_platform": "Win32",
        #     "browser_name": "Chrome",
        #     "browser_version": "138.0.0.0",
        #     "webcast_sdk_version": "2450",
        #     "room_id": "7527483067720583955",
        #     "anchor_id": "3998258005032616",
        #     "sec_anchor_id": "MS4wLjABAAAA2F3NX6RiboGdfcX98Hpp3JESCY-Z8Tw8jQD8aqs25qhdnQSvMyyAbVvnLq5NT_rN",
        #     "ignoreToast": "true",
        #     "rank_type": "30",
        #     "update_scene": "rank_message",
        #     "msToken": "-HpOqCxjx1MRFQP00onCIVOe7UekYXQKcayCMuaffyovdtusmV13ZavT6mmX24sWMlGVdZza4F-MWiGt6iddfmElCqbOu59e-RiUXuBfYxqkbM-OZRHlLQn6dcDCagr8olEfvFxMvSye3lYz4-_pvuAkUQjA-a8oShkGqRiUXlrD",
        #     "a_bogus": "OXsfhHXEd2WbedKSYCY5t53lU8DlNsuyFBiQbinue5Cuch0bDmPtknebJxow1Mjo5SpziCl77EUMbxxb0VXi11HpqmkvS8JWbTICVh8LgqqRTFisEHRTewgEHJebWOJEm5ojJ1k3ItmP2EA4L1riUQAjCAaj4Qkp/rrRda4aNItggzs9FNqxuxSDOXFNBRI4YE=="
        # }
        params.add_param("aid", "6383")
        params.add_param("app_name", "douyin_web")
        params.add_param("live_id", "1")
        params.add_param("device_platform", "web")
        params.add_param("language", "zh-CN")
        params.add_param("enter_from", "web_live")
        params.add_param("cookie_enabled", "true")
        params.add_param("screen_width", get_profile()["screen_width"])
        params.add_param("screen_height", get_profile()["screen_height"])
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_platform", get_profile()["platform"])
        params.add_param("browser_name", get_profile()["browser_name"])
        params.add_param("browser_version", get_profile()["browser_version"])
        params.add_param("webcast_sdk_version", "2450")
        params.add_param("room_id", room_id)
        params.add_param("anchor_id", anchor_id)
        params.add_param("sec_anchor_id", sec_anchor_id)
        params.add_param("ignoreToast", "true")
        params.add_param("rank_type", "30")
        params.add_param("update_scene", "rank_message")
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus(host=LIVE_HOST)
        response = requests.get(url, headers=headers.get(), params=params.get(),
                           cookies=auth.cookie, verify=False)

        check_risk_response(response)
        return response.json()

    @staticmethod
    def get_webcast_detail(auth, user_id, room_id, url: str):
        api = f"/webcast/im/fetch/"
        headers = HeaderBuilder().build(HeaderType.FORM)
        headers.set_header("origin", DouyinAPI.live_url)
        headers.set_referer(url)
        headers.with_csrf(auth.cookie_str)
        params = Params()
        params.add_param("resp_content_type", "protobuf")
        params.add_param("did_rule", "3")
        params.add_param("device_id", "")
        params.add_param("app_name", "douyin_web")
        params.add_param("endpoint", "live_pc")
        params.add_param("support_wrds", "1")
        params.add_param("user_unique_id", str(user_id))
        params.add_param("identity", "audience")
        params.add_param("need_persist_msg_count", "15")
        params.add_param("insert_task_id", "")
        params.add_param("live_reason", "")
        params.add_param("room_id", room_id)
        params.add_param("version_code", "180800")
        params.add_param("last_rtt", "0")
        params.add_param("live_id", "1")
        params.add_param("aid", "6383")
        params.add_param("fetch_rule", "1")
        params.add_param("cursor", "")
        params.add_param("internal_ext", "")
        params.add_param("device_platform", "web")
        params.add_param("cookie_enabled", "true")
        params.add_param("screen_width", get_profile()["screen_width"])
        params.add_param("screen_height", get_profile()["screen_height"])
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_platform", get_profile()["platform"])
        # webcast 这一路的 browser_version 传的是 navigator.appVersion（UA 去掉 Mozilla/ 前缀）
        params.add_param("browser_name", "Mozilla")
        params.add_param("browser_version", get_profile()["ua"].replace("Mozilla/", "", 1))
        params.add_param("browser_online", "true")
        params.add_param("tz_name", "Asia/Shanghai")
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus(host=LIVE_HOST)
        res = requests.get(f'{DouyinAPI.live_url}{api}', headers=headers.get(), params=params.get(),
                           cookies=auth.cookie, verify=False)
        return res.content

    @staticmethod
    def diggLiveRoom(auth, room_id: str, count: str = '1'):
        api = "/webcast/room/like/"
        headers = HeaderBuilder().build(HeaderType.FORM)
        refer = f"https://live.douyin.com/{room_id}"
        headers.set_header("origin", DouyinAPI.douyin_url)
        headers.with_csrf(auth.cookie_str)
        headers.set_referer(refer)
        params = Params()
        params.add_param("aid", '6383')
        params.add_param("app_name", 'douyin_web')
        params.add_param("live_id", '1')
        params.add_param("device_platform", 'web')
        params.add_param("language", 'zh-CN')
        params.add_param("enter_from", 'web_live')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", get_profile()["screen_width"])
        params.add_param("screen_height", get_profile()["screen_height"])
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", get_profile()["browser_name"])
        params.add_param("browser_version", get_profile()["browser_version"])
        params.add_param("room_id", room_id)
        params.add_param("count", count)
        params.add_param("msToken", auth.msToken)
        data = {
        }
        params.with_a_bogus(data)
        res = requests.post(f'{DouyinAPI.live_url}{api}', headers=headers.get(), params=params.get(),
                            cookies=auth.cookie, data=data, verify=False)
        check_risk_response(res)
        return res.json()

    @staticmethod
    def sendMsgInRoom(auth, room_id: str, content: str = ''):
        api = "/webcast/room/chat/"
        headers = HeaderBuilder().build(HeaderType.GET)
        refer = f"https://live.douyin.com/{room_id}"
        headers.set_header("Origin", DouyinAPI.douyin_url)
        headers.with_bd(api, auth)
        headers.with_csrf(auth.cookie_str)
        headers.set_referer(refer)
        params = Params()
        params.add_param("aid", '6383')
        params.add_param("app_name", 'douyin_web')
        params.add_param("live_id", '1')
        params.add_param("device_platform", 'web')
        params.add_param("language", 'zh-CN')
        params.add_param("enter_from", 'web_others_homepage')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", get_profile()["screen_width"])
        params.add_param("screen_height", get_profile()["screen_height"])
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", get_profile()["browser_name"])
        params.add_param("browser_version", get_profile()["browser_version"])
        params.add_param("room_id", room_id)
        params.add_param("content", content)
        params.add_param("type", '0')
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus(host=LIVE_HOST)
        res = requests.get(f'{DouyinAPI.live_url}{api}', headers=headers.get(), params=params.get(),
                           cookies=auth.cookie, verify=False)
        check_risk_response(res)
        return res.json()

    @staticmethod
    def publish_comment(auth, aweme_id: str, content: str = '', reply_id="", **kwargs):
        """
        发布评论
        :param auth: DouyinAuth object.
        :param aweme_id: 作品ID，或作品链接（同项目其它接口都收链接，这里两种都接受）.
        :param content: 评论内容.
        :param reply_id: 回复评论ID.
        :return: JSON.
        """
        api = "/aweme/v1/web/comment/publish"
        # 传链接进来时先解析成数字 ID：否则会把整条 URL 塞进 body 的 aweme_id，
        # 服务端直接返回 status_code=5，且报错完全看不出是参数错
        if "://" in str(aweme_id):
            aweme_id, _url = parse_aweme_id(aweme_id)
        refer = f"https://www.douyin.com/video/{aweme_id}"
        headers = HeaderBuilder().build(HeaderType.FORM)
        headers.set_header("origin", DouyinAPI.douyin_url)
        headers.set_referer(refer)
        headers.with_bd(api, auth)
        headers.with_csrf(auth.cookie_str)
        # uifid 既在 query 也在头里，取自 UIFID Cookie
        uifid = auth.cookie.get('UIFID', '')
        if uifid:
            headers.set_header("uifid", uifid)
        # 顺序与浏览器实测一致：verifyFp/fp 在 msToken 之前，a_bogus 之后只跟 uid
        params = Params()
        params.add_param("app_name", 'aweme')
        params.add_param("enter_from", 'video_detail')
        params.add_param("previous_page", 'video_detail')
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("pc_client_type", '1')
        params.add_param("pc_libra_divert", 'Windows')
        params.add_param("update_version_code", '170400')
        params.add_param("support_h265", '1')
        params.add_param("support_dash", '1')
        params.add_param("version_code", '170400')
        params.add_param("version_name", '17.4.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", get_profile()["screen_width"])
        params.add_param("screen_height", get_profile()["screen_height"])
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", get_profile()["browser_name"])
        params.add_param("browser_version", get_profile()["browser_version"])
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", get_profile()["engine_version"])
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("cpu_core_num", get_profile()["cpu_core_num"])
        params.add_param("device_memory", get_profile()["device_memory"])
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        # 实录 comment/publish 是 50；原来写死 200 是从老代码继承的孤例
        # （全项目只有这里和 get_feed 不是 0/50，2026-08-22 值对账时发现）
        params.add_param("round_trip_time", '50')
        params.with_web_id(auth, refer)
        if uifid:
            params.add_param("uifid", uifid)
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        params.add_param("msToken", auth.msToken)
        data = {
            "aweme_id": aweme_id,
        }
        if reply_id != "":
            data["reply_id"] = reply_id
        data["comment_send_celltime"] = random.randint(1000, 20000)
        data["comment_video_celltime"] = random.randint(1000, 20000)
        data["one_level_comment_rank"] = -1
        data["paste_edit_method"] = "non_paste"
        data["text"] = content
        # 必须是字符串 "[]"：空 list 会被 requests 直接从表单里丢掉，
        # 与参与 a_bogus 计算的 body 对不上
        data["text_extra"] = "[]"
        params.with_a_bogus(data)
        # uid 在 a_bogus 之后追加，不参与签名
        uid = DouyinAPI._comment_uid(auth)
        if uid:
            params.add_param("uid", uid)
        res = requests.post(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), params=params.get(),
                            cookies=auth.cookie, data=data, verify=False)
        check_risk_response(res)
        return res.json()

    @staticmethod
    def _comment_uid(auth):
        """评论接口 query 里的 uid = md5(登录用户数字 ID)。"""
        try:
            return hashlib.md5(str(auth.get_uid()).encode()).hexdigest()
        except Exception:
            return ""

    @staticmethod
    def create_conversation(auth, to_user_id: int, **kwargs):
        """
        创建私信对话.
        :param auth: DouyinAuth object.
        :param to_user_id: 私信对话接收者ID.
        :return: 私信对话ID.
        """
        url = "https://imapi.douyin.com/v2/conversation/create"
        requestProto = ProtoBuilder.build_create_conversation_request(auth, to_user_id, auth.get_uid())
        headers = HeaderBuilder().build(HeaderType.PROTOBUF)
        headers.set_header('referer', 'https://www.douyin.com/')

        resp = requests.post(
            url,
            headers=headers.get(),
            cookies=auth.cookie,
            data=requestProto.SerializeToString(),
            verify=False
        )
        responseProto = ResponseProto.Response()
        responseProto.ParseFromString(resp.content)
        resp_json = protobuf_to_dict(responseProto)
        conversation = resp_json['body']['create_conversation_v2_body']['conversation_info_list'][0]
        conversation_id = conversation['conversation_id']
        conversation_short_id, ticket = int(conversation['conversation_short_id']), conversation['ticket']
        return conversation_id, conversation_short_id, ticket

    @staticmethod
    def get_conversation_list(auth, to_user_id: int, conversation_short_id: int, **kwargs) -> dict:
        """
        取一个私信会话的信息。

        名字里的 list 是历史遗留：接口 `conversation/get_info_list` 一次只查一个会话，
        返回的是这个会话本身的信息。旧实现只抽了 `6.610.1.50.13` 一个字段就返回，
        且注释说是对方的 sec_uid —— 实测那是**会话属主（也就是自己）**的 sec_uid。

        :return: {"conversation_id","conversation_short_id","owner_uid","owner_sec_uid"}，
                 解析失败返回 None。
        """
        import blackboxprotobuf
        url = "https://imapi.douyin.com/v2/conversation/get_info_list"
        requestProto = ProtoBuilder.build_get_conversation_list_info_request(auth, to_user_id, auth.get_uid(), conversation_short_id)
        headers = HeaderBuilder().build(HeaderType.PROTOBUF)
        headers.set_header('referer', 'https://www.douyin.com/')

        resp = requests.post(
            url,
            headers=headers.get(),
            cookies=auth.cookie,
            data=requestProto.SerializeToString(),
            verify=False
        )
        try:
            # 字段名是 blackboxprotobuf 自动推断出来的编号，没有 proto 定义可依
            data, _message_type = blackboxprotobuf.decode_message(resp.content)
            conv = data['6']['610']['1']
            core = conv['50']

            def text(node):
                return node.decode('utf-8') if isinstance(node, bytes) else node

            return {
                "conversation_id": text(conv.get('1')),
                "conversation_short_id": text(conv.get('2')),
                "owner_uid": text(core.get('12')),
                "owner_sec_uid": text(core.get('13')),
            }
        except Exception:
            return None

    @staticmethod
    def get_identity_security_token(auth, force=False, **kwargs):
        """Fetch the short-lived identity token required by PC IM sends.

        The web IM bundle started calling ``/passport/safe/get_identity_security_token/``
        before ``imapi/v1/message/send`` in the 2026 rollout.  The returned
        token is not a Cookie and is instead copied into the protobuf header
        map together with the returned device id.  It is tied to the current
        ticket/dtrait session, so never synthesize it or carry it across Auth
        instances.
        """
        now = time.time()
        cached = str(getattr(auth, 'identity_security_token', '') or '')
        cached_ts = float(getattr(auth, 'identity_security_token_ts', 0) or 0)
        if cached and not force and now - cached_ts < 240:
            return cached, str(getattr(auth, 'identity_security_device_id', '') or '')

        api = '/passport/safe/get_identity_security_token/'
        referer = kwargs.get('referer') or 'https://www.douyin.com/chat?isPopup=1'
        trace_id = uuid.uuid4().hex[:8]
        params = {
            'passport_jssdk_version': '4.2.3',
            'passport_jssdk_type': 'lite',
            'is_from_ttaccountsdk': '1',
            'aid': '6383',
            'language': 'zh',
            'scene': 'web_im',
            'auto_retry_req': '0',
            'skip_verify': 'false',
            'identity_token_force_get_tag': '0',
            'biz_trace_id': trace_id,
            'id_token_version': '1.2.10',
            'msToken': auth.msToken,
        }
        # The browser signs the query before appending a_bogus itself; no
        # verifyFp/fp fields are present on this passport endpoint.
        params['a_bogus'] = generate_a_bogus(
            splice_url(params), host='www.douyin.com'
        )

        headers = HeaderBuilder().build(HeaderType.GET)
        headers.set_referer(referer)
        headers.set_header('accept', 'application/json, text/javascript')
        headers.set_header(
            'x-tt-passport-csrf-token',
            (auth.cookie or {}).get('passport_csrf_token', '')
            or (auth.cookie or {}).get('passport_csrf_token_default', ''),
        )
        headers.set_header('x-tt-passport-trace-id', trace_id)
        # This is a write-adjacent, ticket-protected passport call.  Use the
        # same bd-ticket-guard client-data and dtrait generation as the send
        # request so both requests belong to one security session.
        headers.with_bd(api, auth)

        resp = requests.get(
            f'{DouyinAPI.douyin_url}{api}', params=params,
            headers=headers.get(), cookies=auth.cookie, verify=False,
        )
        check_risk_response(resp)
        try:
            payload = resp.json()
        except Exception as exc:
            raise RuntimeError('身份安全 token 接口返回不可解析响应') from exc
        data = payload.get('data') or {}
        token = str(data.get('identity_security_token') or '')
        device_id = str(data.get('device_id') or '')
        if payload.get('message') not in (None, 'success') or not token:
            error_code = data.get('error_code')
            missing_cookie_hints = [
                name for name in (
                    'UIFID', 'passport_mfa_token', 'x_tt_token',
                    'passport_csrf_token',
                ) if not (auth.cookie or {}).get(name)
            ]
            hint = (
                f'; 当前会话缺少/未同步的浏览器 Cookie: {", ".join(missing_cookie_hints)}'
                if error_code == 3 and missing_cookie_hints else ''
            )
            raise RuntimeError(
                f'身份安全 token 获取失败: {payload!r}{hint}'
            )
        auth.identity_security_token = token
        auth.identity_security_device_id = device_id
        auth.identity_security_token_ts = now
        return token, device_id

    @staticmethod
    def _send_message_raw(auth, conversation_id, conversation_short_id, ticket,
                          message_type, content, *, ext=None,
                          mentioned_users=None, client_message_id=None,
                          **kwargs) -> bool:
        """Send one already-built PC IM message payload.

        Rich-media helpers upload first and call this method with the message
        type/content returned by :class:`DouyinIMMedia`. Keeping one raw send
        path ensures all message types receive the same current ticket-guard,
        identity-security and a_bogus parameters.
        """
        url = 'https://imapi.douyin.com/v1/message/send'
        headers = HeaderBuilder().build(HeaderType.PROTOBUF)
        headers.set_header('referer', 'https://www.douyin.com/')
        headers.with_bd('/v1/message/send', auth)
        identity_token, identity_device_id = DouyinAPI.get_identity_security_token(auth)
        requestProto = ProtoBuilder.build_send_message_request(
            auth, conversation_id, conversation_short_id, ticket,
            content=content, message_type=message_type, ext=ext,
            mentioned_users=mentioned_users, client_message_id=client_message_id,
            identity_security_token=identity_token,
            identity_security_device_id=identity_device_id,
        )
        # Browser order is msToken -> a_bogus -> verifyFp -> fp.  Only the
        # first field participates in the a_bogus input for this endpoint.
        params = {'msToken': auth.msToken}
        params['a_bogus'] = generate_a_bogus(
            splice_url(params), host='www.douyin.com'
        )
        params['verifyFp'] = auth.cookie['s_v_web_id']
        params['fp'] = auth.cookie['s_v_web_id']
        resp = requests.post(url, params=params, headers=headers.get(), verify=False, cookies=auth.cookie,
                             data=requestProto.SerializeToString())
        responseProto = ResponseProto.Response()
        responseProto.ParseFromString(resp.content)
        resp_json = protobuf_to_dict(responseProto)
        success = resp_json.get('message') == 'OK'
        if success:
            logger.info(f'私信发送成功 conversation_id={conversation_id}')
        else:
            logger.error(f'私信发送失败 {resp_json}')
        return success

    @staticmethod
    def send_msg(auth, conversation_id, conversation_short_id, ticket,
                 content: str, **kwargs) -> bool:
        """发送文本私信（兼容旧调用）。"""
        if isinstance(content, dict):
            payload = content
        else:
            payload = {
                "aweType": 700,
                "type": 0,
                "richTextInfos": [],
                "text": str(content),
            }
        return DouyinAPI._send_message_raw(
            auth, conversation_id, conversation_short_id, ticket, DouyinAPI.IM_TEXT, payload,
            **kwargs,
        )

    send_text = send_msg

    @staticmethod
    def send_image(auth, conversation_id, conversation_short_id, ticket,
                   image, **kwargs) -> bool:
        """Upload and send one image attachment (message type 27)."""
        from dy_apis.douyin_im_media import DouyinIMMedia
        upload_kwargs = {
            key: kwargs.pop(key) for key in ("user_id", "gif", "proxies")
            if key in kwargs
        }
        payload = DouyinIMMedia.upload_image(auth, image, **upload_kwargs)
        return DouyinAPI._send_message_raw(
            auth, conversation_id, conversation_short_id, ticket, DouyinAPI.IM_STORY_PICTURE, payload,
            **kwargs,
        )

    @staticmethod
    def send_video(auth, conversation_id, conversation_short_id, ticket,
                   video, *, thumb=None, **kwargs) -> bool:
        """Upload and send one video attachment (message type 30)."""
        from dy_apis.douyin_im_media import DouyinIMMedia
        upload_kwargs = {
            key: kwargs.pop(key) for key in ("user_id", "proxies")
            if key in kwargs
        }
        payload = DouyinIMMedia.upload_video(auth, video, thumb=thumb, **upload_kwargs)
        return DouyinAPI._send_message_raw(
            auth, conversation_id, conversation_short_id, ticket, DouyinAPI.IM_STORY_VIDEO, payload,
            **kwargs,
        )

    @staticmethod
    def send_audio(auth, conversation_id, conversation_short_id, ticket,
                   audio, *, encrypted=True, content=None, **kwargs) -> bool:
        """Upload and send a voice message.

        ``content`` can be supplied when a captured client-specific voice
        payload is available.  Otherwise the uploader's generic encrypted
        voice payload is used (type 109); server acceptance can vary by account
        experiment, so callers should handle a False return value.
        """
        if content is None:
            raise NotImplementedError(
                "当前 PC IM 网页端没有语音录制/上传协议；"
                "请传入兼容客户端捕获的 voice content dict（content=...）"
            )
        message_type = DouyinAPI.IM_ENCRYPT_VOICE if encrypted else DouyinAPI.IM_VOICE
        return DouyinAPI._send_message_raw(
            auth, conversation_id, conversation_short_id, ticket,
            message_type, content, **kwargs,
        )

    @staticmethod
    def send_file(auth, conversation_id, conversation_short_id, ticket,
                  file, **kwargs) -> bool:
        """Upload and send a generic file attachment (legacy type 6)."""
        from dy_apis.douyin_im_media import DouyinIMMedia
        upload_kwargs = {
            key: kwargs.pop(key) for key in ("user_id", "proxies")
            if key in kwargs
        }
        payload = DouyinIMMedia.upload_file(auth, file, **upload_kwargs)
        return DouyinAPI._send_message_raw(
            auth, conversation_id, conversation_short_id, ticket, DouyinAPI.IM_FILE, payload,
            **kwargs,
        )

    @staticmethod
    def send_sticker(auth, conversation_id, conversation_short_id, ticket,
                     sticker=None, **kwargs) -> bool:
        """Send a BIG_EMOJI payload (type 5).

        ``sticker`` should be the complete CDN metadata dict.  For convenience
        callers may pass ``image_id``/``uri`` and the helper will construct the
        browser-compatible envelope; arbitrary local images are not silently
        mislabeled as platform stickers.
        """
        from dy_apis.douyin_im_media import DouyinIMMedia
        if sticker is None:
            sticker = DouyinIMMedia.sticker_content(
                image_id=kwargs.pop("image_id"), uri=kwargs.pop("uri"),
                display_name=kwargs.pop("display_name", ""),
                image_type=kwargs.pop("image_type", "gif"),
                width=kwargs.pop("width", 0), height=kwargs.pop("height", 0),
                package_id=kwargs.pop("package_id", 0),
                url_list=kwargs.pop("url_list", None),
            )
        return DouyinAPI._send_message_raw(
            auth, conversation_id, conversation_short_id, ticket, DouyinAPI.IM_BIG_EMOJI, sticker,
            **kwargs,
        )

    send_emoji = send_sticker

    @staticmethod
    def send_card(auth, conversation_id, conversation_short_id, ticket,
                  message_type, content, **kwargs) -> bool:
        """Send a caller-supplied share/card payload with an explicit type."""
        return DouyinAPI._send_message_raw(
            auth, conversation_id, conversation_short_id, ticket,
            int(message_type), content, **kwargs,
        )

    @staticmethod
    def _share_detail(auth, content):
        """Resolve a URL to an aweme detail while retaining dict payloads."""
        if isinstance(content, str):
            value = content.strip()
            if value.startswith(("http://", "https://")):
                response = DouyinAPI.get_work_info(auth, value)
                detail = response.get("aweme_detail") if isinstance(response, dict) else None
                if isinstance(detail, dict):
                    return detail
                if isinstance(response, dict):
                    return response
                raise RuntimeError("作品详情接口返回了不可用的数据")
        return content

    @staticmethod
    def _share_uid(auth):
        try:
            return str(auth.get_uid() or "")
        except Exception:
            return ""

    @staticmethod
    def send_share_aweme(auth, conversation_id, conversation_short_id, ticket,
                         content, **kwargs) -> bool:
        from dy_apis.douyin_im_media import DouyinIMMedia
        card_kwargs = {
            key: kwargs.pop(key) for key in ("uid", "sec_uid", "name", "title",
                                             "item_id", "share_id", "timestamp")
            if key in kwargs
        }
        if "uid" not in card_kwargs:
            card_kwargs["uid"] = DouyinAPI._share_uid(auth)
        payload = DouyinIMMedia.build_share_aweme_content(
            DouyinAPI._share_detail(auth, content), **card_kwargs,
        )
        return DouyinAPI.send_card(
            auth, conversation_id, conversation_short_id, ticket, DouyinAPI.IM_SHARE_AWEME, payload,
            **kwargs,
        )

    @staticmethod
    def send_share_photos(auth, conversation_id, conversation_short_id, ticket,
                          content, **kwargs) -> bool:
        from dy_apis.douyin_im_media import DouyinIMMedia
        card_kwargs = {
            key: kwargs.pop(key) for key in ("uid", "sec_uid", "name", "title",
                                             "item_id", "share_id", "timestamp",
                                             "image_count", "image_index")
            if key in kwargs
        }
        if "uid" not in card_kwargs:
            card_kwargs["uid"] = DouyinAPI._share_uid(auth)
        payload = DouyinIMMedia.build_share_photos_content(
            DouyinAPI._share_detail(auth, content), **card_kwargs,
        )
        return DouyinAPI.send_card(
            auth, conversation_id, conversation_short_id, ticket, DouyinAPI.IM_SHARE_PHOTOS, payload,
            **kwargs,
        )

    @staticmethod
    def send_share_web(auth, conversation_id, conversation_short_id, ticket,
                       content, **kwargs) -> bool:
        from dy_apis.douyin_im_media import DouyinIMMedia
        card_kwargs = {
            key: kwargs.pop(key) for key in ("title", "desc", "cover_url", "link_url")
            if key in kwargs
        }
        payload = DouyinIMMedia.build_share_web_content(content, **card_kwargs)
        return DouyinAPI.send_card(
            auth, conversation_id, conversation_short_id, ticket, DouyinAPI.IM_SHARE_WEB, payload,
            **kwargs,
        )

    @staticmethod
    def send_user_card(auth, conversation_id, conversation_short_id, ticket,
                       content, **kwargs) -> bool:
        from dy_apis.douyin_im_media import DouyinIMMedia
        card_kwargs = {
            key: kwargs.pop(key) for key in ("uid", "sec_uid", "name", "avatar",
                                             "cover_items", "cover_url")
            if key in kwargs
        }
        payload = DouyinIMMedia.build_user_card_content(content, **card_kwargs)
        return DouyinAPI.send_card(
            auth, conversation_id, conversation_short_id, ticket, DouyinAPI.IM_SHARE_USER, payload,
            **kwargs,
        )

    @staticmethod
    def get_device_id(auth, **kwargs) -> str:
        """
        获取设备ID.
        :param auth: DouyinAuth object.
        :return: 设备ID.
        """
        url = "https://www.douyin.com/aweme/v1/web/query/user"
        headers = HeaderBuilder().build(HeaderType.GET)
        refer = "https://www.douyin.com/discover"
        headers.set_header("referer", refer)
        headers.with_uifid(auth)
        params = Params()
        (params
         .with_platform()
         .add_param("publish_video_strategy_type", "2")
         .with_web_id(auth, refer)
         .with_ms_token()
         .add_param('verifyFp', auth.cookie['s_v_web_id'])
         .add_param('fp', auth.cookie['s_v_web_id'])
         .with_a_bogus()
         )
        resp = requests.get(url, params=params.get(), verify=False, headers=headers.get(), cookies=auth.cookie)
        check_risk_response(resp)
        resp_json = resp.json()
        return resp_json['id']

    @staticmethod
    def digg(auth, aweme_id: str, digg_type: str = '1', **kwargs) -> bool:
        """
        点赞视频.
        :param auth: DouyinAuth object.
        :param aweme_id: 作品ID，或作品链接.
        :param digg_type: 点赞类型, 1: 点赞, 0: 取消点赞.
        :return: 操作是否成功.
        """
        api = '/aweme/v1/web/commit/item/digg/'
        if "://" in str(aweme_id):
            aweme_id, _url = parse_aweme_id(aweme_id)
        url = f'{DouyinAPI.douyin_url}{api}'
        refer = f'{DouyinAPI.douyin_url}/discover?modal_id={aweme_id}'
        headers = HeaderBuilder.build(HeaderType.FORM)
        # 实录：digg 不带 Host，bd 是只读 4 个头（无 client-data），带 x-tt-session-dtrait
        headers.with_bd_readonly(auth)
        # 实录 digg 带 x-tt-session-dtrait（写接口的风控头），只读 bd 头不含它
        _dt = auth.session_dtrait_header(api)
        if _dt:
            headers.set_header('x-tt-session-dtrait', _dt)
        headers.with_csrf(auth.cookie_str)
        headers.with_uifid(auth)
        headers.set_header("origin", DouyinAPI.douyin_url)
        headers.set_header("referer", refer)
        params = Params()
        params.with_platform(round_trip_time='0')
        params.with_web_id(auth, refer)
        params.with_uifid(auth)
        params.with_verify_fp(auth)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        # 实录 query 末尾还有 uid（登录用户的数字 uid）
        # 实录 uid = md5(登录用户数字 ID)，与评论接口同一套
        params.add_param("uid", DouyinAPI._comment_uid(auth))
        data = {
            'aweme_id': aweme_id,
            'item_type': '0',
            'type': digg_type,
        }
        resp = requests.post(url, params=params.get(), headers=headers.get(), cookies=auth.cookie, data=data,
                             verify=False)
        check_risk_response(resp)
        resp_json = resp.json()
        # 响应里的 is_digg 是**操作前**的状态（点赞后回 0、取消后回 1），
        # 拿它当返回值只有点赞方向碰巧是对的，取消永远返回 False。以 status_code 为准。
        return resp_json.get('status_code') == 0

    @staticmethod
    def search_some_video_work(auth, query: str, num: int = 16, sort_type: str = '0', publish_time: str = '0',
                               filter_duration="", search_range="0", **kwargs) -> tuple:
        """
        搜索视频频道作品.
        :param auth: DouyinAuth object.
        :param query: 搜索关键字.
        :param num: 搜索结果数量.
        :param sort_type: 排序方式 0 综合排序 1 最多点赞 2 最新发布.
        :param publish_time: 发布时间 0 不限 1 一天内 7 一周内 180 半年内.
        :param filter_duration: 视频时长 空字符串 不限 0-1 一分钟内 1-5 1-5分钟内 5-10000 5分钟以上
        :param search_range: 搜索范围 0 不限 3 关注的人 1 最近看过 2 还未看过
        :return: 作品列表, 引导词.
        """
        offset = "0"
        count = "25"
        search_id = ""
        video_work_list = []
        while True:
            search_id, guide_search_words, res_json = DouyinAPI.search_video_work(auth, query, offset, count, sort_type,
                                                                                  publish_time, filter_duration,
                                                                                  search_range, search_id)
            video_works = res_json["data"]
            video_work_list.extend(video_works)
            if res_json["has_more"] != 1 or len(video_work_list) >= num:
                break
            offset = str(int(offset) + int(count))
        if len(video_work_list) > num:
            video_work_list = video_work_list[:num]
        return video_work_list, guide_search_words

    @staticmethod
    def search_video_work(auth, query: str, offset: str = '0', count: str = '16', sort_type: str = '0',
                          publish_time: str = '0', filter_duration="", search_range="0", search_id="", **kwargs):
        """
        搜索视频频道作品.
        :param auth: DouyinAuth object.
        :param query: 搜索关键字.
        :param offset: 搜索结果偏移量.
        :param count: 搜索结果数量.
        :param sort_type: 排序方式 0 综合排序 1 最多点赞 2 最新发布.
        :param publish_time: 发布时间 0 不限 1 一天内 7 一周内 180 半年内.
        :param filter_duration: 视频时长 空字符串 不限 0-1 一分钟内 1-5 1-5分钟内 5-10000 5分钟以上
        :param search_range: 搜索范围 0 不限 3 关注的人 1 最近看过 2 还未看过
        :return: 下个搜索ID, 引导词, JSON数据.
        """
        api = "/aweme/v1/web/search/item/"
        headers = HeaderBuilder().build(HeaderType.GET)
        refer = f'https://www.douyin.com/search/{urllib.parse.quote(query)}?aid={uuid.uuid4()}&type=video'
        headers.set_referer(refer)
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("search_channel", 'aweme_video_web')
        params.add_param("enable_history", '1')
        params.add_param("sort_type", sort_type)
        params.add_param("publish_time", publish_time)
        params.add_param("filter_duration", filter_duration)
        params.add_param("search_range", search_range)
        params.add_param("keyword", query)
        params.add_param("search_source", 'normal_search')
        params.add_param("query_correct_type", '1')
        params.add_param("is_filter_search", '1')
        params.add_param("from_group_id", '')
        params.add_param("offset", offset)
        params.add_param("count", count)
        params.add_param("need_filter_settings", '1' if offset == '0' else '0')
        if search_id != "":
            params.add_param("search_id", search_id)
        params.add_param("list_type", 'single')
        # 实录：list_type 之后是 pc_search_top_1_params（空值），再进公共组
        params.add_param("pc_search_top_1_params", '')
        # with_platform() 里已经有 effective_type / round_trip_time，
        # 原来后面又 add_param 覆盖一遍（0 被改成 50），读代码时极易误判实际值。
        # 直接把想要的值作为参数传进去。
        params.with_platform(round_trip_time='50')
        params.with_web_id(auth, refer)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        search_id = resp.headers["X-Tt-Logid"]
        check_risk_response(resp)
        json_data = resp.json()
        return search_id, json_data["guide_search_words"], json_data


if __name__ == '__main__':
    web_protect_str = r''
    keys_str = r''
    cookies_str = ''



    from builder.auth import DouyinAuth
    auth_ = DouyinAuth()
    auth_.perepare_auth(cookies_str, web_protect_str, keys_str)

    live_url = "https://live.douyin.com/852953608964"
    live_id = "852953608964"
    res = DouyinAPI.get_live_info(auth_, live_id)
    print(res)

    room_id = res['room_id']
    anchor_id = res['anchor_id']
    sec_anchor_id = res['sec_uid']
    DouyinAPI.get_rank_list(auth_, room_id, anchor_id, sec_anchor_id)



    # res = DouyinAPI.search_live(auth_, "三角洲")
    # # print(res)
    # for i in res['data']:
    #     print(i['lives']['author']['nickname'])
    #     live_id = re.findall(r'"web_rid":"(.*?)",', str(i['lives']))[0]
    #     live_url = f'https://live.douyin.com/{live_id}'
    #     print(live_url)

    # my_uid = DouyinAPI.get_my_uid(auth_)
    # print(my_uid)
    # my_sec_uid = DouyinAPI.get_my_sec_uid(auth_)
    # print(my_sec_uid)
    # work_url = r'https://www.douyin.com/video/7433523124836060416'
    # print(DouyinAPI.get_user_info(auth_, "https://www.douyin.com/user/MS4wLjABAAAA7BDbZk0LjnEMcDDsLag5mDrMc157hD3x0SMhH1HaCM8"))
    # print(DouyinAPI.digg(auth_, "7433523124836060416", "1"))
    # print(DouyinAPI.digg(auth_, "7212619184386182435", "1"))
    # user_info = DouyinAPI.get_user_info(auth_, "https://www.douyin.com/user/MS4wLjABAAAAHXtdycTLMSe5Ld_468-9HKR1HUUrk4ywq-xMCM-E9w_cDIrhmynrQUalv061ZSpn?from_tab_name=main")
    # to_user_id = user_info['user']['uid']
    # conversation_id, conversation_short_id, ticket = DouyinAPI.create_conversation(auth_, to_user_id)
    # content = r'有份长期通告寻求合作，你通过了前期筛选，我是项目负责人，期待你与我联系：ncyj12'
    # DouyinAPI.send_msg(auth_, conversation_id, conversation_short_id, ticket, content)
    # print(DouyinAPI.get_user_all_work_info(auth_,"https://www.douyin.com/user/MS4wLjABAAAA8nC7nKxMrRtBwEqFzRgRBSxhBcw89VL0ysN-IXvhlKU?vid=7378825215213718818"))
    # print(DouyinAPI.get_work_info(auth_, "https://www.douyin.com/video/7212619184386182435"))
    # print(DouyinAPI.get_work_all_out_comment(auth_, "https://www.douyin.com/video/7212619184386182435"))
    # print(DouyinAPI.get_work_inner_comment(auth_, {
    #     "aweme_id": "7212619184386182435",
    #     "cid": "7327990109411902208"
    # }, "0"))
    # print(DouyinAPI.get_work_all_inner_comment(auth_, {
    #     "aweme_id": "7212619184386182435",
    #     "cid": "7327990109411902208"
    # }))
    # print(DouyinAPI.get_work_all_comment(auth_, "https://www.douyin.com/video/7212619184386182435"))
    # print(DouyinAPI.search_general_work(auth_, "美女", sort_type='2'))
    # print(DouyinAPI.search_some_general_work(auth_, "美女", sort_type='2', publish_time='0', num=30))
    # print(DouyinAPI.get_all_live_production(auth_, "https://live.douyin.com/84255891276"))
    # 60503986163 289606013148 91819894158
    # room_info = DouyinAPI.get_live_info(auth_, '60503986163')
    # print(room_info)
    # print(DouyinAPI.get_live_production(auth_, "https://live.douyin.com/84255891276", room_id, author_id, '0'))
    # print(DouyinAPI.collect_aweme(auth_, "7377676120549772554", '1'))
    # print(DouyinAPI.move_collect_aweme(auth_, "7207861673711930656", "tt", "7379252593215919891"))
    # print(DouyinAPI.remove_collect_aweme(auth_, "7376244589235113250", "tt", "7379252593215919891"))
    # print(DouyinAPI.get_live_production_detail(auth_, "https://live.douyin.com/552370739330", "3622058069401408240", "MS4wLjABAAAATfhR-kvE-AWqZaNaomCLFqgDKzvBwMS87FUGVjS_u7Y", "7379220637308504843"))
    # print(DouyinAPI.get_collect_list(auth_))
    # print(DouyinAPI.search_user(auth_, "巴旦木公主"))
    # print(DouyinAPI.search_some_user(auth_, "巴旦木公主", 30))
    # print(DouyinAPI.search_live(auth_, "馨馨baby😐ᵇᵃᵇʸ"))
    # print(DouyinAPI.get_user_favorite(auth_, "MS4wLjABAAAA99bTJ_GOw3odYmsXOe7i7xuEv0iQf2X_Kg_VUyVP0U8"))
    # print(DouyinAPI.get_some_user_follower_list(auth_, "3074704605975950", "MS4wLjABAAAA0L4jpkJDeuFO9AM-dQK1B649tmr7GIw-sQtyPasP_Z45QnUjIQgUOLIs8Kw8Gp-u", 40))
    # print(DouyinAPI.get_some_user_following_list(auth_, "3074704605975950", "MS4wLjABAAAA0L4jpkJDeuFO9AM-dQK1B649tmr7GIw-sQtyPasP_Z45QnUjIQgUOLIs8Kw8Gp-u", 40))
    # print(DouyinAPI.search_some_video_work(auth_, "巴旦木公主", 32))
    # print(DouyinAPI.get_feed(auth_))
    # print(DouyinAPI.publish_comment(auth_, "7356193166732709139"))
    # print(DouyinAPI.get_upload_auth_key(auth_))

    # while True:
    #     print(DouyinAPI.sendMsgInRoom(auth_, room_id, "666"))
    #     time.sleep(3)
    # #
    # while True:
    #     print(DouyinAPI.diggLiveRoom(auth_, room_id, '10'))
    #     time.sleep(1)
