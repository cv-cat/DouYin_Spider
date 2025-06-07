import json
import random
import re
import time
import urllib
import uuid

import requests
requests.packages.urllib3.disable_warnings()
from bs4 import BeautifulSoup
from protobuf_to_dict import protobuf_to_dict

import static.Response_pb2 as ResponseProto
from builder.header import HeaderBuilder, HeaderType
from builder.params import Params
from builder.proto import ProtoBuilder
from utils.dy_util import splice_url, generate_a_bogus, generate_msToken, trans_cookies



class DouyinAPI:
    douyin_url = 'https://www.douyin.com'
    live_url = 'https://live.douyin.com'
    creator = "https://creator.douyin.com"


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
        params.add_param("update_version_code", '170400')
        params.add_param("pc_client_type", '1')
        params.add_param("version_code", '290100')
        params.add_param("version_name", '29.1.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", '1707')
        params.add_param("screen_height", '960')
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", 'Edge')
        params.add_param("browser_version", '125.0.0.0')
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", '125.0.0.0')
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("cpu_core_num", '32')
        params.add_param("device_memory", '8')
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        params.add_param("round_trip_time", '100')
        params.with_web_id(auth, user_url)
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        params.add_param("msToken",
                         auth.msToken)
        params.with_a_bogus()
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        return json.loads(resp.text)

    @staticmethod
    def get_work_info(auth, url: str) -> dict:
        """
        获取作品信息.
        :param auth: DouyinAuth object.
        :param url: 作品URL.
        :return: JSON.
        """
        api = f"/aweme/v1/web/aweme/detail/"
        if 'video' in url:
            aweme_id = url.split("/")[-1].split("?")[0]
        else:
            aweme_id = re.findall(r'modal_id=(\d+)', url)[0]
            url = f'https://www.douyin.com/video/{aweme_id}'
        headers = HeaderBuilder().build(HeaderType.GET)
        headers.set_referer(url)
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("aweme_id", aweme_id)
        params.add_param("update_version_code", "170400")
        params.add_param("pc_client_type", "1")
        params.add_param("version_code", "190500")
        params.add_param("version_name", "19.5.0")
        params.add_param("cookie_enabled", "true")
        params.add_param("screen_width", "1707")
        params.add_param("screen_height", "960")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_platform", "Win32")
        params.add_param("browser_name", "Edge")
        params.add_param("browser_version", "125.0.0.0")
        params.add_param("browser_online", "true")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", "125.0.0.0")
        params.add_param("os_name", "Windows")
        params.add_param("os_version", "10")
        params.add_param("cpu_core_num", "32")
        params.add_param("device_memory", "8")
        params.add_param("platform", "PC")
        params.add_param("downlink", "4.75")
        params.add_param("effective_type", "4g")
        params.add_param("round_trip_time", "150")
        params.with_web_id(auth, url)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        resp_json = json.loads(resp.text)
        return resp_json

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
        if 'video' in url:
            aweme_id = url.split("/")[-1].split("?")[0]
        else:
            aweme_id = re.findall(r'modal_id=(\d+)', url)[0]
            url = f'https://www.douyin.com/video/{aweme_id}'
        headers = HeaderBuilder().build(HeaderType.GET)
        headers.set_referer(url)
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("aweme_id", aweme_id)
        params.add_param("cursor", cursor)
        params.add_param("count", "5")
        params.add_param("item_type", "0")
        params.add_param("whale_cut_token", "")
        params.add_param("cut_version", "1")
        params.add_param("rcFT", "")
        params.add_param("update_version_code", "170400")
        params.add_param("pc_client_type", "1")
        params.add_param("version_code", "170400")
        params.add_param("version_name", "17.4.0")
        params.add_param("cookie_enabled", "true")
        params.add_param("screen_width", "1707")
        params.add_param("screen_height", "960")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_platform", "Win32")
        params.add_param("browser_name", "Edge")
        params.add_param("browser_version", "125.0.0.0")
        params.add_param("browser_online", "true")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", "125.0.0.0")
        params.add_param("os_name", "Windows")
        params.add_param("os_version", "10")
        params.add_param("cpu_core_num", "32")
        params.add_param("device_memory", "8")
        params.add_param("platform", "PC")
        params.add_param("downlink", "10")
        params.add_param("effective_type", "4g")
        params.add_param("round_trip_time", "0")
        params.with_web_id(auth, url)
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        resp_json = json.loads(resp.text)
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
        params.add_param("update_version_code", "170400")
        params.add_param("pc_client_type", "1")
        params.add_param("version_code", "170400")
        params.add_param("version_name", "17.4.0")
        params.add_param("cookie_enabled", "true")
        params.add_param("screen_width", "1707")
        params.add_param("screen_height", "960")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_platform", "Win32")
        params.add_param("browser_name", "Edge")
        params.add_param("browser_version", "125.0.0.0")
        params.add_param("browser_online", "true")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", "125.0.0.0")
        params.add_param("os_name", "Windows")
        params.add_param("os_version", "10")
        params.add_param("cpu_core_num", "32")
        params.add_param("device_memory", "8")
        params.add_param("platform", "PC")
        params.add_param("downlink", "10")
        params.add_param("effective_type", "4g")
        params.add_param("round_trip_time", "0")
        params.with_web_id(auth, refer)
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        resp_json = json.loads(resp.text)
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
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("publish_video_strategy_type", '2')
        params.add_param("source", 'channel_pc_web')
        params.add_param("sec_user_id", user_id)
        params.add_param("personal_center_strategy", '1')
        params.add_param("update_version_code", '170400')
        params.add_param("pc_client_type", '1')
        params.add_param("version_code", '170400')
        params.add_param("version_name", '17.4.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", '1707')
        params.add_param("screen_height", '960')
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", 'Edge')
        params.add_param("browser_version", '125.0.0.0')
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", '125.0.0.0')
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("cpu_core_num", '32')
        params.add_param("device_memory", '8')
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        params.add_param("round_trip_time", '100')
        params.with_web_id(auth, user_url)
        params.add_param("msToken", auth.msToken)
        params.add_param('verifyFp', auth.cookie['s_v_web_id'])
        params.add_param('fp', auth.cookie['s_v_web_id'])
        params.with_a_bogus()
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        return json.loads(resp.text)

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
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("search_channel", "aweme_general")
        params.add_param("enable_history", "1")
        params.add_param("filter_selected", r'{"sort_type":"%s","publish_time":"%s","filter_duration":"%s",'
                                            r'"search_range":"%s","content_type":"%s"}' % (sort_type, publish_time,
                                                                                           filter_duration,
                                                                                           search_range, content_type))
        params.add_param("keyword", query)
        params.add_param("search_source", "tab_search")
        params.add_param("query_correct_type", "1")
        params.add_param("is_filter_search", "1")
        params.add_param("from_group_id", "")
        params.add_param("offset", offset)
        params.add_param("count", '25')
        params.add_param("need_filter_settings", '1' if offset == '0' else '0')
        params.add_param("list_type", "single")
        params.add_param("update_version_code", "170400")
        params.add_param("pc_client_type", "1")
        params.add_param("version_code", "190600")
        params.add_param("version_name", "19.6.0")
        params.add_param("cookie_enabled", "true")
        params.add_param("screen_width", "1707")
        params.add_param("screen_height", "960")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_platform", "Win32")
        params.add_param("browser_name", "Edge")
        params.add_param("browser_version", "125.0.0.0")
        params.add_param("browser_online", "true")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", "125.0.0.0")
        params.add_param("os_name", "Windows")
        params.add_param("os_version", "10")
        params.add_param("cpu_core_num", "32")
        params.add_param("device_memory", "8")
        params.add_param("platform", "PC")
        params.add_param("downlink", "10")
        params.add_param("effective_type", "4g")
        params.add_param("round_trip_time", "50")
        params.with_web_id(auth, refer)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        return json.loads(resp.text)

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
            works = res_json["data"]
            work_list.extend(works)
            if res_json["has_more"] != 1 or len(work_list) >= num:
                break
            offset = str(int(offset) + len(works))
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
        api = "/aweme/v1/web/discover/search"
        headers = HeaderBuilder().build(HeaderType.GET)
        refer = f'https://www.douyin.com/search/{urllib.parse.quote(query)}?aid={uuid.uuid4()}&type=general'
        headers.set_referer(refer)
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("search_channel", 'aweme_user_web')
        params.add_param("search_filter_value", r'{"douyin_user_fans":["%s"],"douyin_user_type":["%s"]}' % (
            douyin_user_fans, douyin_user_type))
        params.add_param("keyword", query)
        params.add_param("search_source", 'switch_tab')
        params.add_param("query_correct_type", '1')
        params.add_param("is_filter_search", '1')
        # params.add_param("from_group_id", '7378456704385600820')
        params.add_param("offset", offset)
        params.add_param("count", num)
        params.add_param("need_filter_settings", '1' if offset == '0' else '0')
        params.add_param("list_type", 'single')
        params.add_param("update_version_code", '170400')
        params.add_param("pc_client_type", '1')
        params.add_param("version_code", '170400')
        params.add_param("version_name", '17.4.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", '1707')
        params.add_param("screen_height", '960')
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", 'Edge')
        params.add_param("browser_version", '125.0.0.0')
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", '125.0.0.0')
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("cpu_core_num", '32')
        params.add_param("device_memory", '8')
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        params.add_param("round_trip_time", '150')
        params.with_web_id(auth, refer)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
        return resp.json()

    @staticmethod
    def search_live(auth, query: str, offset: str = '0', num: str = '25', **kwargs):
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
        params.add_param("offset", offset)
        params.add_param("count", num)
        params.add_param("need_filter_settings", '1' if offset == '0' else '0')
        params.add_param("list_type", 'single')
        params.add_param("update_version_code", '170400')
        params.add_param("pc_client_type", '1')
        params.add_param("version_code", '170400')
        params.add_param("version_name", '17.4.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", '1707')
        params.add_param("screen_height", '960')
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", 'Edge')
        params.add_param("browser_version", '125.0.0.0')
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", '125.0.0.0')
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("cpu_core_num", '32')
        params.add_param("device_memory", '8')
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        params.add_param("round_trip_time", '50')
        params.with_web_id(auth, refer)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        resp = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), cookies=auth.cookie,
                            params=params.get(), verify=False)
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
        count = "25"
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
        params = Params()
        params.add_param("device_platform", 'webapp')
        params.add_param("aid", '6383')
        params.add_param("channel", 'channel_pc_web')
        params.add_param("sec_user_id", 'MS4wLjABAAAA99bTJ_GOw3odYmsXOe7i7xuEv0iQf2X_Kg_VUyVP0U8')
        params.add_param("max_cursor", max_cursor)
        params.add_param("min_cursor", '0')
        params.add_param("whale_cut_token", '')
        params.add_param("cut_version", '1')
        params.add_param("count", num)
        params.add_param("publish_video_strategy_type", '2')
        params.add_param("update_version_code", '170400')
        params.add_param("pc_client_type", '1')
        params.add_param("version_code", '170400')
        params.add_param("version_name", '17.4.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", '1707')
        params.add_param("screen_height", '960')
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", 'Edge')
        params.add_param("browser_version", '125.0.0.0')
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", '125.0.0.0')
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("cpu_core_num", '32')
        params.add_param("device_memory", '8')
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        params.add_param("round_trip_time", '100')
        params.with_web_id(auth=auth, url=refer)
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        params.add_param("msToken",
                         auth.msToken)
        params.with_a_bogus()
        response = requests.get('https://www.douyin.com/aweme/v1/web/aweme/favorite/', params=params.get(),
                                headers=headers.get(), cookies=auth.cookie,
                                verify=False)
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
        params = Params()
        params.with_platform()
        params.with_web_id(auth, refer)
        params.with_ms_token()
        params.add_param('verifyFp', auth.cookie['s_v_web_id'])
        params.add_param('fp', auth.cookie['s_v_web_id'])
        params.with_a_bogus()
        resp = requests.get(url, params=params.get(), verify=False, headers=headers.get(), cookies=auth.cookie)
        resp_json = json.loads(resp.text)
        return int(resp_json['user_uid'])

    @staticmethod
    def get_my_sec_uid(auth, **kwargs) -> str:
        """
        获取自己的SECID.
        :param auth: DouyinAuth object.
        :return: SECID.
        """
        headers = HeaderBuilder().build(HeaderType.GET)
        url = "https://www.douyin.com/user/self"
        params = {
            "from_tab_name": "main"
        }
        response = requests.get(url, headers=headers.get(), cookies=auth.cookie, params=params)
        sec_uid = re.findall(r'\\"secUid\\":\\"(.*?)\\"', response.text)[0]
        return sec_uid


    @staticmethod
    def get_live_info(auth_, live_id, **kwargs):
        """
        获取直播间信息.
        :param live_id: 直播间ID
        :return: 直播间ID, 用户ID, ttwid
        """
        url = "https://live.douyin.com/" + live_id
        headers = HeaderBuilder().build(HeaderType.GET)
        res = requests.get(url, headers=headers.get(), cookies=auth_.cookie, verify=False)
        ttwid = res.cookies.get_dict()['ttwid']
        soup = BeautifulSoup(res.text, 'html.parser')
        scripts = soup.select('script[nonce]')
        for script in scripts:
            if script.string is not None and 'roomId' in script.string:
                try:
                    room_id = re.findall(r'\\"roomId\\":\\"(\d+)\\"', script.string)[0]
                    user_id = re.findall(r'\\"user_unique_id\\":\\"(\d+)\\"', script.string)[0]
                    room_info = re.findall(r'\\"roomInfo\\":\{\\"room\\":\{\\"id_str\\":\\".*?\\",\\"status\\":(.*?),\\"status_str\\":\\".*?\\",\\"title\\":\\"(.*?)\\"', script.string)[0]
                    room_status = room_info[0]
                    room_title = room_info[1]
                    return {
                        "room_id": room_id,
                        "user_id": user_id,
                        "ttwid": ttwid,
                        # 2 是直播中 4 是未开播
                        "room_status": room_status,
                        "room_title": room_title
                    }
                except Exception as e:
                    pass
        return None, None, None

    @staticmethod
    def get_live_production(auth, url: str, room_id: str, author_id: str, offset: str, **kwargs):
        """
        获取直播间的商品信息.
        :param auth: DouyinAuth object.
        :param url: 直播间链接.
        :param room_id: 直播间ID
        :param author_id: 主播ID
        :param offset: 翻页游标.
        :return: JSON 商品列表.
        """
        api = f"/live/promotions/page/"
        headers = HeaderBuilder().build(HeaderType.GET)
        headers.set_header("origin", DouyinAPI.live_url)
        headers.set_referer(url)
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("room_id", room_id)
        params.add_param("author_id", author_id)
        params.add_param("offset", offset)
        params.add_param("limit", "20")
        params.add_param("pc_client_type", "1")
        params.add_param("version_code", "210800")
        params.add_param("version_name", "21.8.0")
        params.add_param("cookie_enabled", "true")
        params.add_param("screen_width", "2560")
        params.add_param("screen_height", "1440")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_platform", "Win32")
        params.add_param("browser_name", "Edge")
        params.add_param("browser_version", "121.0.0.0")
        params.add_param("browser_online", "true")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", "121.0.0.0")
        params.add_param("os_name", "Windows")
        params.add_param("os_version", "10")
        params.add_param("cpu_core_num", "20")
        params.add_param("device_memory", "8")
        params.add_param("platform", "PC")
        params.add_param("downlink", "10")
        params.add_param("effective_type", "4g")
        params.add_param("round_trip_time", "50")
        params.with_web_id(auth, url)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        res = requests.post(f'{DouyinAPI.live_url}{api}', headers=headers.get(), cookies=auth.cookie,
                           params=params.get(), verify=False)
        return res.json()

    @staticmethod
    def get_all_live_production(auth, url: str, **kwargs):
        """
        获取直播间的所有商品信息.
        :param auth: DouyinAuth object.
        :param url: 直播间链接.
        :return:
        """
        room_info = DouyinAPI.get_live_info(auth, url.split("/")[-1].split("?")[0])
        room_id = room_info["room_id"]
        author_id = room_info["author_id"]
        offset = "0"
        production_list = []
        while True:
            res_json = DouyinAPI.get_live_production(auth, url, room_id, author_id, offset)
            productions = res_json["promotions"]
            production_list.extend(productions)
            offset = str(res_json["next_offset"])
            if offset == "-1":
                break
        return production_list

    @staticmethod
    def get_live_production_detail(auth, url, ec_promotion_id, sec_author_id, live_room_id, **kwargs):
        """
        获取直播间商品详情.
        :param auth: DouyinAuth object.
        :param url: 直播间链接.
        :param ec_promotion_id: 商品ID.
        :param sec_author_id: 主播ID
        :param live_room_id: 直播间ID
        :return: JSON 商品详情.
        """
        api = f"/ecom/product/detail/saas/pc/"
        headers = HeaderBuilder().build(HeaderType.FORM)
        headers.set_header("origin", DouyinAPI.live_url)
        headers.set_referer(url)
        headers.with_csrf(auth.cookie_str)
        params = Params()
        params.add_param("is_h5", "1")
        params.add_param("origin_type", "638301")
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("pc_client_type", "1")
        params.add_param("update_version_code", "170400")
        params.add_param("version_code", "")
        params.add_param("version_name", "")
        params.add_param("cookie_enabled", "true")
        params.add_param("screen_width", "1707")
        params.add_param("screen_height", "960")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_platform", "Win32")
        params.add_param("browser_name", "Edge")
        params.add_param("browser_version", "125.0.0.0")
        params.add_param("browser_online", "true")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", "125.0.0.0")
        params.add_param("os_name", "Windows")
        params.add_param("os_version", "10")
        params.add_param("cpu_core_num", "32")
        params.add_param("device_memory", "8")
        params.add_param("platform", "PC")
        params.add_param("downlink", "1.7")
        params.add_param("effective_type", "4g")
        params.add_param("round_trip_time", "200")
        params.with_web_id(auth, url)
        params.add_param("msToken", auth.msToken)
        data = {
            "bff_type": "2",
            "ec_promotion_id": ec_promotion_id,
            "is_h5": "1",
            "item_id": "0",
            "live_room_id": live_room_id,
            "origin_type": "638301",
            "promotion_ids": ec_promotion_id,
            "room_id": live_room_id,
            "sec_author_id": sec_author_id,
            "use_new_price": "1"
        }
        params.with_a_bogus(data)
        res = requests.post(f'{DouyinAPI.live_url}{api}', headers=headers.get(), params=params.get(),
                            cookies=auth.cookie, data=data, verify=False)
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
        headers.with_bd(api, auth)
        headers.with_csrf(auth.cookie_str)
        headers.set_header("origin", DouyinAPI.douyin_url)
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("pc_client_type", "1")
        params.add_param("update_version_code", "170400")
        params.add_param("version_code", "170400")
        params.add_param("version_name", "17.4.0")
        params.add_param("cookie_enabled", "true")
        params.add_param("screen_width", "1707")
        params.add_param("screen_height", "960")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_platform", "Win32")
        params.add_param("browser_name", "Edge")
        params.add_param("browser_version", "125.0.0.0")
        params.add_param("browser_online", "true")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", "125.0.0.0")
        params.add_param("os_name", "Windows")
        params.add_param("os_version", "10")
        params.add_param("cpu_core_num", "32")
        params.add_param("device_memory", "8")
        params.add_param("platform", "PC")
        params.add_param("downlink", "10")
        params.add_param("effective_type", "4g")
        params.add_param("round_trip_time", "50")
        params.with_web_id(auth, refer)
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        params.add_param("msToken", auth.msToken)
        data = {
            "action": action,
            "aweme_id": aweme_id,
            "aweme_type": "0",
        }
        params.with_a_bogus(data)
        res = requests.post(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), params=params.get(),
                            cookies=auth.cookie, data=data, verify=False)
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
        headers.with_bd(api, auth)
        headers.with_csrf(auth.cookie_str)
        headers.set_header("origin", DouyinAPI.douyin_url)
        params = Params()
        params.add_param("aid", "6383")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_name", "Edge")
        params.add_param("browser_online", "true")
        params.add_param("browser_platform", "Win32")
        params.add_param("browser_version", "125.0.0.0")
        params.add_param("channel", "channel_pc_web")
        params.add_param("collects_name", collect_name)
        params.add_param("cookie_enabled", "true")
        params.add_param("cpu_core_num", "32")
        params.add_param("device_memory", "8")
        params.add_param("device_platform", "webapp")
        params.add_param("downlink", "10")
        params.add_param("effective_type", "4g")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", "125.0.0.0")
        params.add_param("item_ids", aweme_id)
        params.add_param("item_type", "2")
        params.add_param("move_collects_list", collect_id)
        params.add_param("os_name", "Windows")
        params.add_param("os_version", "10")
        params.add_param("pc_client_type", "1")
        params.add_param("platform", "PC")
        params.add_param("round_trip_time", "50")
        params.add_param("screen_height", "960")
        params.add_param("screen_width", "1707")
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
        headers.with_bd(api, auth)
        headers.with_csrf(auth.cookie_str)
        headers.set_header("origin", DouyinAPI.douyin_url)
        params = Params()
        params.add_param("aid", "6383")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_name", "Edge")
        params.add_param("browser_online", "true")
        params.add_param("browser_platform", "Win32")
        params.add_param("browser_version", "125.0.0.0")
        params.add_param("channel", "channel_pc_web")
        params.add_param("collects_name", collect_name)
        params.add_param("cookie_enabled", "true")
        params.add_param("cpu_core_num", "32")
        params.add_param("device_memory", "8")
        params.add_param("device_platform", "webapp")
        params.add_param("downlink", "10")
        params.add_param("effective_type", "4g")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", "125.0.0.0")
        params.add_param("from_collects_id", collect_id)
        params.add_param("item_ids", aweme_id)
        params.add_param("item_type", "2")
        params.add_param("os_name", "Windows")
        params.add_param("os_version", "10")
        params.add_param("pc_client_type", "1")
        params.add_param("platform", "PC")
        params.add_param("round_trip_time", "50")
        params.add_param("screen_height", "960")
        params.add_param("screen_width", "1707")
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
        refer = "https://www.douyin.com/?recommend=1"
        headers.set_referer(refer)
        params = Params()
        params.add_param("device_platform", "webapp")
        params.add_param("aid", "6383")
        params.add_param("channel", "channel_pc_web")
        params.add_param("cursor", "0")
        params.add_param("count", "20")
        params.add_param("update_version_code", "170400")
        params.add_param("pc_client_type", "1")
        params.add_param("version_code", "170400")
        params.add_param("version_name", "17.4.0")
        params.add_param("cookie_enabled", "true")
        params.add_param("screen_width", "1707")
        params.add_param("screen_height", "960")
        params.add_param("browser_language", "zh-CN")
        params.add_param("browser_platform", "Win32")
        params.add_param("browser_name", "Edge")
        params.add_param("browser_version", "125.0.0.0")
        params.add_param("browser_online", "true")
        params.add_param("engine_name", "Blink")
        params.add_param("engine_version", "125.0.0.0")
        params.add_param("os_name", "Windows")
        params.add_param("os_version", "10")
        params.add_param("cpu_core_num", "32")
        params.add_param("device_memory", "8")
        params.add_param("platform", "PC")
        params.add_param("downlink", "5.95")
        params.add_param("effective_type", "4g")
        params.add_param("round_trip_time", "200")
        params.with_web_id(auth, refer)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        res = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), params=params.get(),
                           cookies=auth.cookie, verify=False)
        return res.json()

    @staticmethod
    def get_user_follower_list(auth, user_id: str, sec_id: str, max_time: str = '0', count: str = '20', **kwargs):
        """
        获取用户的粉丝列表
        :param auth: DouyinAuth object.
        :param user_id: 用户ID.
        :param sec_id: 用户sec_id.
        :param max_time: 最大时间戳.
        :param count: 数量.
        :return:  JSON.
        """
        api = "/aweme/v1/web/user/follower/list/"
        headers = HeaderBuilder().build(HeaderType.GET)
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
        params.add_param("update_version_code", '170400')
        params.add_param("pc_client_type", '1')
        params.add_param("version_code", '170400')
        params.add_param("version_name", '17.4.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", '1707')
        params.add_param("screen_height", '960')
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", 'Edge')
        params.add_param("browser_version", '125.0.0.0')
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", '125.0.0.0')
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("cpu_core_num", '32')
        params.add_param("device_memory", '8')
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        params.add_param("round_trip_time", '150')
        params.with_web_id(auth, refer)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        res = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), params=params.get(),
                           cookies=auth.cookie, verify=False)
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
            followers = res_json["followers"]
            follower_list.extend(followers)
            if res_json["has_more"] != 1 or len(follower_list) >= num:
                break
            max_time = res_json["min_time"]
        if len(follower_list) > num:
            follower_list = follower_list[:num]
        return follower_list

    @staticmethod
    def get_user_following_list(auth, user_id: str, sec_id: str, max_time: str = '0', count: str = '20', **kwargs):
        """
        获取用户的关注列表
        :param auth: DouyinAuth object.
        :param user_id: 用户ID.
        :param sec_id: 用户sec_id.
        :param max_time: 最大时间戳.
        :param count: 数量.
        :return:
        """
        api = "/aweme/v1/web/user/following/list/"
        headers = HeaderBuilder().build(HeaderType.GET)
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
        params.add_param("is_top", '1')
        params.add_param("update_version_code", '170400')
        params.add_param("pc_client_type", '1')
        params.add_param("version_code", '170400')
        params.add_param("version_name", '17.4.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", '1707')
        params.add_param("screen_height", '960')
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", 'Edge')
        params.add_param("browser_version", '125.0.0.0')
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", '125.0.0.0')
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("cpu_core_num", '32')
        params.add_param("device_memory", '8')
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        params.add_param("round_trip_time", '150')
        params.with_web_id(auth, refer)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        res = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), params=params.get(),
                           cookies=auth.cookie, verify=False)
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
            followings = res_json["followings"]
            following_list.extend(followings)
            if res_json["has_more"] != 1 or len(following_list) >= num:
                break
            max_time = res_json["min_time"]
        if len(following_list) > num:
            following_list = following_list[:num]
        return following_list

    @staticmethod
    def get_notice_list(auth, min_time='0', max_time='0', count='10', notice_group='700', **kwargs):
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
        params.add_param("update_version_code", '170400')
        params.add_param("pc_client_type", '1')
        params.add_param("version_code", '170400')
        params.add_param("version_name", '17.4.0')
        params.add_param("cookie_enabled", 'true')
        params.add_param("screen_width", '1707')
        params.add_param("screen_height", '960')
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", 'Edge')
        params.add_param("browser_version", '125.0.0.0')
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", '125.0.0.0')
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("cpu_core_num", '32')
        params.add_param("device_memory", '8')
        params.add_param("platform", 'PC')
        params.add_param("downlink", '10')
        params.add_param("effective_type", '4g')
        params.add_param("round_trip_time", '50')
        params.with_web_id(auth, refer)
        params.add_param("msToken", auth.msToken)
        params.with_a_bogus()
        params.add_param("verifyFp", auth.cookie['s_v_web_id'])
        params.add_param("fp", auth.cookie['s_v_web_id'])
        res = requests.get(f'{DouyinAPI.douyin_url}{api}', headers=headers.get(), params=params.get(),
                           cookies=auth.cookie, verify=False)
        return res.json()

    @staticmethod
    def get_some_notice_list(auth, num: int = 20, notice_group='700', **kwargs) -> list:
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
        params.add_param("screen_width", '1707')
        params.add_param("screen_height", '960')
        params.add_param("browser_language", 'zh-CN')
        params.add_param("browser_platform", 'Win32')
        params.add_param("browser_name", 'Edge')
        params.add_param("browser_version", '125.0.0.0')
        params.add_param("browser_online", 'true')
        params.add_param("engine_name", 'Blink')
        params.add_param("engine_version", '125.0.0.0')
        params.add_param("os_name", 'Windows')
        params.add_param("os_version", '10')
        params.add_param("cpu_core_num", '32')
        params.add_param("device_memory", '8')
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
        return res.json()



if __name__ == '__main__':
    web_protect_str = r''
    keys_str = r''
    cookies_str = ''



    from builder.auth import DouyinAuth
    auth_ = DouyinAuth()
    auth_.perepare_auth(cookies_str, web_protect_str, keys_str)

    res = DouyinAPI.search_live(auth_, "三角洲")
    # print(res)
    for i in res['data']:
        print(i['lives']['author']['nickname'])
        live_id = re.findall(r'"web_rid":"(.*?)",', str(i['lives']))[0]
        live_url = f'https://live.douyin.com/{live_id}'
        print(live_url)

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