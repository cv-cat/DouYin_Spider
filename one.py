import json
import re
import requests
from dy_utils.dy_util import download_media, check_and_create_path, norm_str, get_headers, handle_video_info, check_info, save_video_detail

class OneVideo:
    def __init__(self, info=None):
        if info is None:
            self.info = check_info()
        else:
            self.info = info
        self.headers = get_headers()

    # 单个视频
    def get_one_video_info(self, url):
        try:
            response = requests.get(url, headers=self.headers, cookies={"s_v_web_id": self.info['cookies']["s_v_web_id"]})
            html_text = response.text
            video_info = re.findall('<script id="RENDER_DATA" type="application/json">(.*?)</script>', html_text, re.S)[0]
        except:
            response = requests.get(url, headers=self.headers, cookies=self.info['cookies'])
            html_text = response.text
            video_info = re.findall('<script id="RENDER_DATA" type="application/json">(.*?)</script>', html_text, re.S)[0]
        video_info = requests.utils.unquote(video_info)
        video_info_json = json.loads(video_info)
        video = handle_video_info(video_info_json)
        return video

    # cover 是否覆盖
    def save_one_video_info(self, url, need_cover=False):
        video = self.get_one_video_info(url)
        nickname = norm_str(video.nickname)
        sec_uid = video.sec_uid
        title = norm_str(video.title)
        if len(title) > 50:
            title = title[:50]
        if title.strip() == '':
            title = f'无标题'
        path = f'./datas/{nickname}_{sec_uid}/{title}_{video.awemeId}'
        exist = check_and_create_path(path)
        if exist and not need_cover:
            print(f'用户: {nickname}, 标题: {title} 本地已存在，跳过保存')
            return video
        save_video_detail(path, video)
        if len(video.images) > 0:
            for img_index, image in enumerate(video.images):
                download_media(path, f'image_{img_index}', image['urlList'][0], 'image', f'第{img_index}张图片')
        else:
            download_media(path, 'cover', video.video_cover, 'image', '视频封面')
        download_media(path, 'video', video.video_addr, 'video')
        print(f'用户: {nickname}, 标题: {title} 信息保存成功')
        print('===================================================================')
        return video

    def main(self, url_list):
        for url in url_list:
            try:
                self.save_one_video_info(url)
            except:
                print(f'视频 {url} 查询失败')


if __name__ == '__main__':
    one_video = OneVideo()
    url_list = [
        'https://www.douyin.com/user/MS4wLjABAAAAp2OG100fRV13HqBbRnbPM_l7DU0eTOaxgL-4_l07fQo?modal_id=7149358157217795368',
        'https://www.douyin.com/user/MS4wLjABAAAAup3S7EWeZIeBM0-qnT6YmI2nMI4KUtOqiuJBasbbm3o?modal_id=7166141112820747551',
        'https://www.douyin.com/user/MS4wLjABAAAAh7MdVA-UbMYLeO3_zhA_Z-Mrkh8cDwBCU_qQqucnrFE?modal_id=7137966302055894306',
    ]
    one_video.main(url_list)

