import json
import re
import time
import os
import execjs
import requests
from dy_utils.cookie_utils import get_new_cookies
from pojo.video import Video_Detail
from pojo.user import User_Detail
js = execjs.compile(open(r'./static/dy.js', 'r', encoding='gb18030').read())

def download_media(path, name, url, type, info=''):
    # 5次错误机会
    for i in range(5):
        try:
            if type == 'image':
                # print(f"{info}图片开始下载, {url}")
                print(f"{info}图片开始下载")
                content = requests.get(url).content
                with open(path + '/' + name + '.jpg', mode="wb") as f:
                    f.write(content)
                    print(f"{info}图片下载完成")
            elif type == 'video':
                print(f"{name}开始下载, {url}")
                start_time = time.time()
                res = requests.get(url, stream=True)
                size = 0
                chunk_size = 1024 * 1024
                content_size = int(res.headers["content-length"])
                with open(path + '/' + name + '.mp4', mode="wb") as f:
                    for data in res.iter_content(chunk_size=chunk_size):
                        f.write(data)
                        size += len(data)
                        percentage = size / content_size
                        print(f'\r视频:%.2fMB\t' % (content_size / 1024 / 1024),
                              '下载进度:[%-50s%.2f%%]耗时: %.1fs, ' % ('>' * int(50 * percentage), percentage * 100, time.time() - start_time),
                              end='')
                    print(f"{name}下载完成")
            break
        except:
            print(f"第{i+1}次下载失败，重新下载, 剩余{4-i}次机会")
            continue

def timestamp_to_str(timestamp):
    time_local = time.localtime(timestamp)
    dt = time.strftime("%Y-%m-%d %H:%M:%S", time_local)
    return dt

def check_and_create_path(path):
    if not os.path.exists(path):
        os.makedirs(path)
        return False
    return True

def check_path(path):
    if not os.path.exists(path):
        return False
    return True

def norm_str(str):
    new_str = re.sub(r"|[\\/:*?\"<>| ]+", "", str).replace('\n', '').replace('\r', '')
    return new_str

def splice_url(params):
    splice_url_str = ''
    for key, value in params.items():
        if value is None:
            value = ''
        splice_url_str += key + '=' + value + '&'
    return splice_url_str[:-1]

def get_dir_list(path):
    name_list = os.listdir(path)
    dir_list = []
    for name in name_list:
        # 只保留文件夹
        if os.path.isdir(f'{path}\\{name}'):
            dir_list.append(name)
    return dir_list

def get_all_video_awemeId(path):
    dir_list = get_dir_list(path)
    aweme_id_list = []
    for dir in dir_list:
        aweme_id_list.append(dir.split('_')[-1])
    return aweme_id_list

def get_headers():
    return {
        "authority": "www.douyin.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": "https://www.douyin.com/user/MS4wLjABAAAAigSKToDtKeC5cuZ3YsDrHfYuvpLqVSygIZ0m0yXfUAI",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"117\", \"Not;A=Brand\";v=\"8\", \"Chromium\";v=\"117\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.47"
    }

def get_cookies_temp():
    return {}
    # return {
    #     "s_v_web_id": "verify_ln8pqqpx_SoWehCw2_SBbP_4iJ3_8RcD_l3aFlgKdqXCX",
    #     "ttwid": "1%7C_3kNH5A-9Unug-ME67YnduhZkcbd7M_pS15I5xzIJxw%7C1696240413%7C7b2df9ccc4d62d16ac7d3121cd38ae8a04979fa11729e3f066345d97a7b87b87",
    # }

def get_cookies():
    pass
    # return {
    #     'ttwid': '1%7COxU_rA3MGrFsx3b2FmTpOj886AZefFyxi7tihScSz9Y%7C1696327685%7C322bcfbd4d8abf941b53edefaec22cc4e7ad3295c31429bfa448ca81bc9843a5',
    # }

def get_list_params():
    return {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "sec_user_id": "",
        "max_cursor": "0",
        "locate_query": "false",
        "show_live_replay_strategy": "1",
        "need_time_list": "1",
        "time_list_query": "0",
        "whale_cut_token": "",
        "cut_version": "1",
        "count": "18",
        "publish_video_strategy_type": "2",
        "pc_client_type": "1",
        "version_code": "170400",
        "version_name": "17.4.0",
        "cookie_enabled": "true",
        "screen_width": "1707",
        "screen_height": "1067",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Edge",
        "browser_version": "117.0.2045.47",
        "browser_online": "true",
        "engine_name": "Blink",
        "engine_version": "117.0.0.0",
        "os_name": "Windows",
        "os_version": "10",
        "cpu_core_num": "20",
        "device_memory": "8",
        "platform": "PC",
        "downlink": "10",
        "effective_type": "4g",
        "round_trip_time": "50",
        # "webid": "7285297037532612107",
        "webid": "",
        "msToken": "",
    }

def get_profile_params():
    return {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "publish_video_strategy_type": "2",
        "source": "channel_pc_web",
        "sec_user_id": "",
        "pc_client_type": "1",
        "version_code": "170400",
        "version_name": "17.4.0",
        "cookie_enabled": "true",
        "screen_width": "1707",
        "screen_height": "1067",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Edge",
        "browser_version": "117.0.2045.47",
        "browser_online": "true",
        "engine_name": "Blink",
        "engine_version": "117.0.0.0",
        "os_name": "Windows",
        "os_version": "10",
        "cpu_core_num": "20",
        "device_memory": "8",
        "platform": "PC",
        "downlink": "10",
        "effective_type": "4g",
        "round_trip_time": "50",
        # "webid": "7285671865124996668",
        "webid": "",
        "msToken": "",
    }

def get_search_params():
    return {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "search_channel": "aweme_general",
        "sort_type": "0",
        "publish_time": "0",
        "keyword": "阔澜 可以点评四周的风景",
        "search_source": "normal_search",
        "query_correct_type": "1",
        "is_filter_search": "0",
        "from_group_id": "",
        # "offset": "15",
        # "count": "25",
        # "search_id": "202310162344486FA7398D503D9C3E9846",
        "pc_client_type": "1",
        "version_code": "190600",
        "version_name": "19.6.0",
        "cookie_enabled": "true",
        "screen_width": "1707",
        "screen_height": "1067",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Edge",
        "browser_version": "118.0.2088.46",
        "browser_online": "true",
        "engine_name": "Blink",
        "engine_version": "118.0.0.0",
        "os_name": "Windows",
        "os_version": "10",
        "cpu_core_num": "20",
        "device_memory": "8",
        "platform": "PC",
        "downlink": "10",
        "effective_type": "4g",
        "round_trip_time": "50",
        "webid": "",
        "msToken": "",
    }
def correct_url(url):
    if url.startswith('//'):
        url = 'https:' + url
    elif url.startswith('https:'):
        pass
    else:
        url = 'https://' + url
    return url


def handle_video_info(data):
    awemeId = data['app']['videoDetail']['awemeId']
    sec_uid = data['app']['videoDetail']['authorInfo']['secUid']
    nickname = data['app']['videoDetail']['authorInfo']['nickname']
    author_avatar = 'https:' + data['app']['videoDetail']['authorInfo']['avatarUri']
    video_cover = 'https:' + data['app']['videoDetail']['video']['cover']
    title = data['app']['videoDetail']['desc']
    desc = data['app']['videoDetail']['desc']
    digg_count = data['app']['videoDetail']['stats']['diggCount']
    comment_count = data['app']['videoDetail']['stats']['commentCount']
    collect_count = data['app']['videoDetail']['stats']['collectCount']
    share_count = data['app']['videoDetail']['stats']['shareCount']
    addr = 'https:' + data['app']['videoDetail']['video']['playAddr'][0]['src']
    images = data['app']['videoDetail']['images']
    if not isinstance(images, list):
        images = []
    upload_time = data['app']['videoDetail']['createTime']
    video_detail = Video_Detail(None, awemeId, sec_uid, nickname, author_avatar, video_cover, title, desc, digg_count, comment_count, collect_count, share_count, addr, images, upload_time)
    return video_detail

def handle_list_video_info_each(data):
    awemeId = data['aweme_id']
    sec_uid = data['author']['sec_uid']
    nickname = data['author']['nickname']
    author_avatar = data['author']['avatar_thumb']['url_list'][0]
    video_cover = data['video']['cover']['url_list'][0]
    title = data['desc']
    desc = data['desc']
    digg_count = data['statistics']['digg_count']
    commnet_count = data['statistics']['comment_count']
    collect_count = data['statistics']['collect_count']
    share_count = data['statistics']['share_count']
    video_addr = data['video']['play_addr']['url_list'][0]
    images = data['images']
    if not isinstance(images, list):
        images = []
    upload_time = data['create_time']
    video_detail = Video_Detail(None, awemeId, sec_uid, nickname, author_avatar, video_cover, title, desc, digg_count, commnet_count, collect_count, share_count, video_addr, images, upload_time)
    return video_detail

def handle_search_info_each(data):
    awemeId = data['aweme_id']
    sec_uid = data['author']['sec_uid']
    nickname = data['author']['nickname']
    author_avatar = data['author']['avatar_thumb']['url_list'][0]
    video_cover = data['video']['cover']['url_list'][0]
    title = data['desc']
    desc = data['desc']
    digg_count = data['statistics']['digg_count']
    commnet_count = data['statistics']['comment_count']
    collect_count = data['statistics']['collect_count']
    share_count = data['statistics']['share_count']
    video_addr = data['video']['play_addr']['url_list'][0]
    images = data['images']
    if not isinstance(images, list):
        images = []
    upload_time = data['create_time']
    video_detail = Video_Detail(None, awemeId, sec_uid, nickname, author_avatar, video_cover, title, desc, digg_count, commnet_count, collect_count, share_count, video_addr, images, upload_time)
    return video_detail
def handle_profile_info(data):
    sec_uid = data['user']['sec_uid']
    nickname = data['user']['nickname']
    author_avatar = data['user']['avatar_larger']['url_list'][0]
    desc = data['user']['signature']
    following_count = data['user']['following_count']
    follower_count = data['user']['follower_count']
    total_favorited = data['user']['total_favorited']
    aweme_count = data['user']['aweme_count']
    unique_id = data['user']['unique_id']
    user_age = data['user']['user_age']
    gender = data['user']['gender']
    if gender == 1:
        gender = '男'
    elif gender == 0:
        gender = '女'
    else:
        gender = '未知'
    try:
        ip_location = data['user']['ip_location']
    except:
        ip_location = '未知'
    user_detail = User_Detail(None, sec_uid, nickname, author_avatar, desc, following_count, follower_count, total_favorited, aweme_count,unique_id, user_age, gender, ip_location)
    return user_detail

def save_user_detail(path, user):
    with open(path + '/detail.txt', mode="w", encoding="utf-8") as f:
        f.write(f"主页url: {f'https://www.douyin.com/user/{user.sec_uid}'}\n")
        f.write(f"用户名: {user.nickname}\n")
        f.write(f"介绍: {user.desc}\n")
        f.write(f"关注数量: {user.following_count}\n")
        f.write(f"粉丝数量: {user.follower_count}\n")
        f.write(f"作品被赞数量: {user.total_favorited}\n")
        f.write(f"作品数量: {user.aweme_count}\n")
        f.write(f"抖音号: {user.unique_id}\n")
        f.write(f"年龄: {user.user_age}\n")
        f.write(f"性别: {user.gender}\n")
        f.write(f"ip归属地: {user.ip_location}\n")

def save_video_detail(path, video):
    with open(path + '/' + 'detail.txt', mode="w", encoding="utf-8") as f:
        f.write(f"视频url: {f'https://www.douyin.com/user/{video.sec_uid}?modal_id={video.awemeId}'}\n")
        f.write(f"视频标题: {video.title}\n")
        f.write(f"视频描述: {video.desc}\n")
        f.write(f"视频点赞数量: {video.digg_count}\n")
        f.write(f"视频评论数量: {video.comment_count}\n")
        f.write(f"视频收藏数量: {video.collect_count}\n")
        f.write(f"视频分享数量: {video.share_count}\n")
        f.write(f"视频上传时间: {timestamp_to_str(video.upload_time)}\n")
def check_info():
    print('获取cookie时请关闭chrome浏览器），若cookie获取成功后仍运行失败，请清空static下的info.json文件，重新运行程序')
    headers = get_headers()
    if not os.path.exists("./static/info.json"):
        open('./static/info.json', 'w')
    test_user_url = 'https://www.douyin.com/user/MS4wLjABAAAAEpmH344CkCw2M58T33Q8TuFpdvJsOyaZcbWxAMc6H03wOVFf1Ow4mPP94TDUS4Us'
    with open("./static/info.json", "r", encoding="utf-8") as f:
        info = f.read()
    try:
        profile_url = "https://www.douyin.com/aweme/v1/web/user/profile/other/"
        info = json.loads(info)
        sec_user_id = test_user_url.split('/')[-1]
        params = get_profile_params()
        params['webid'] = info['webid']
        params['msToken'] = info['msToken']
        params['sec_user_id'] = sec_user_id
        splice_url_str = splice_url(params)
        xs = js.call('get_dy_xb', splice_url_str)
        params['X-Bogus'] = xs
        post_url = profile_url + '?' + splice_url(params)
        response = requests.get(post_url, headers=headers, cookies=info['cookies'])
        profile_json = response.json()
        print('cookie有效')
        return info
    except:
        print("cookie和其他信息失效，正在重新获取中...请等待，若时间超过20秒，重新运行程序")
        info = get_new_cookies()
        print("cookie和其他信息获取成功")
        with open("./static/info.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(info))
        return info



