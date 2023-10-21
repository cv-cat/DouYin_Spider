import requests

from dy_utils.dy_util import js, get_headers, get_search_params, splice_url, check_info, handle_search_info_each, download_media, check_and_create_path, norm_str, save_video_detail


class Search:
    def __init__(self, info=None):
        if info is None:
            self.info = check_info()
        else:
            self.info = info
        self.search_url = "https://www.douyin.com/aweme/v1/web/general/search/single/"
        self.headers = get_headers()

    def get_search_data(self, query, number, sort_type='0'):
        params = get_search_params()
        params['sort_type'] = sort_type
        params['keyword'] = query
        params['count'] = '25'
        params['webid'] = self.info['webid']
        splice_url_str = splice_url(params)
        xs = js.call('get_dy_xb', splice_url_str)
        params['X-Bogus'] = xs
        video_list = []
        while len(video_list) < number:
            response = requests.get(self.search_url, headers=self.headers, cookies=self.info['cookies'], params=params)
            res = response.json()
            for item in res['data']:
                if item['type'] == 1:
                    try:
                        video_detail = handle_search_info_each(item['aweme_info'])
                        video_list.append(video_detail)
                        if len(video_list) >= number:
                            break
                    except:
                        continue
            if not res['has_more']:
                print(f'搜索结果数量为 {len(video_list)}, 不足 {number}')
                break
            params['offset'] = str(int(params.get('offset', 0)) + 10)
            params['count'] = '10'
        return video_list

    def save_search_data(self, query, number, sort_type, publish_time, need_cover=False):
        params = get_search_params()
        params['sort_type'] = sort_type
        params['publish_time'] = publish_time
        params['keyword'] = query
        params['count'] = '25'
        params['webid'] = self.info['webid']
        splice_url_str = splice_url(params)
        xs = js.call('get_dy_xb', splice_url_str)
        params['X-Bogus'] = xs
        index = 0
        while index < number:
            response = requests.get(self.search_url, headers=self.headers, cookies=self.info['cookies'], params=params)
            res = response.json()
            for item in res['data']:
                if item['type'] == 1:
                    try:
                        video_detail = handle_search_info_each(item['aweme_info'])
                        self.save_one_video_info(video_detail, need_cover)
                        index += 1
                        if index >= number:
                            break
                    except:
                        continue
            if not res['has_more']:
                print(f'搜索结果数量为 {index}, 不足 {number}')
                break
            params['offset'] = str(int(params.get('offset', 0)) + 10)
            params['count'] = '10'
        print(f'搜索结果全部下载完成，共 {index} 个视频')

    # 工具类，用于保存信息
    def save_one_video_info(self, video, need_cover=False):
        try:
            title = norm_str(video.title)
            if title.strip() == '':
                title = f'无标题'
            path = f'./search_datas/{video.nickname}_{video.sec_uid}/{title}_{video.awemeId}'
            exist = check_and_create_path(path)
            if exist and not need_cover:
                print(f'用户: {video.nickname}, 标题: {title} 本地已存在，跳过保存')
                return
            save_video_detail(path, video)
            if len(video.images) > 0:
                for img_index, image in enumerate(video.images):
                    download_media(path, f'image_{img_index}', image['url_list'][0], 'image', f'第{img_index}张图片')
            else:
                download_media(path, 'cover', video.video_cover, 'image', '视频封面')
            download_media(path, 'video', video.video_addr, 'video')
            print(f'用户: {video.nickname}, 标题: {title} 保存成功')
        except:
            print(f'用户: {video.nickname}, 标题: {norm_str(video.title)} 保存失败')


    def main(self, info):
        query = info['query']
        number = info['number']
        sort_type = info['sort_type']
        publish_time = info['publish_time']
        self.save_search_data(query, number, sort_type, publish_time)


if __name__ == '__main__':
    search = Search()
    # 搜索关键词
    query = '阔澜 可以点评四周的风景'
    # 0 智能排序, type='1' 热门排序, type='2' 最新排序
    sort_type = '0'
    # 搜索的数量（前多少个）
    number = 20
    # 0为不限时间，其余数字为限制时间，如1是1天内的视频，666是666天内的视频
    publish_time = '0'
    info = {
        'query': query,
        'number': number,
        'sort_type': sort_type,
        'publish_time': publish_time,
    }
    search.main(info)
