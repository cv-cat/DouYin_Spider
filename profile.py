import requests
from dy_utils.dy_util import js, get_headers, get_profile_params, splice_url, handle_profile_info, check_info, download_media, check_and_create_path, norm_str, save_user_detail

class Profile:
    def __init__(self, info=None):
        if info is None:
            self.info = check_info()
        else:
            self.info = info
        self.headers = get_headers()
        self.profile_url = "https://www.douyin.com/aweme/v1/web/user/profile/other/"
    # 个人信息主页
    def get_profile_info(self, url):
        sec_user_id = url.split('/')[-1]
        params = get_profile_params()
        params['webid'] = self.info['webid']
        params['msToken'] = self.info['msToken']
        params['sec_user_id'] = sec_user_id
        splice_url_str = splice_url(params)
        xs = js.call('get_dy_xb', splice_url_str)
        params['X-Bogus'] = xs
        post_url = self.profile_url + '?' + splice_url(params)
        response = requests.get(post_url, headers=self.headers, cookies=self.info['cookies'])
        profile_json = response.json()
        profile = handle_profile_info(profile_json)
        return profile

    def save_profile_info(self, url):
        profile = self.get_profile_info(url)
        print(f'开始保存用户{profile.nickname}基本信息')
        sec_uid = profile.sec_uid
        nickname = norm_str(profile.nickname)
        path = f'./datas/{nickname}_{sec_uid}'
        check_and_create_path(path)
        download_media(path, 'avatar', profile.author_avatar, 'image', '用户头像')
        save_user_detail(path, profile)
        print(f'User {nickname} 信息保存成功')
        return profile


def main():
    profile = Profile()
    user_url_list = [
        'https://www.douyin.com/user/MS4wLjABAAAAaixF5AEGRf0aSd46-AMnHwLOp1T0iAEx_lTDDJeGx_QJHgn_8SYGZv3p3zT6Oyk8',
        'https://www.douyin.com/user/MS4wLjABAAAAEpmH344CkCw2M58T33Q8TuFpdvJsOyaZcbWxAMc6H03wOVFf1Ow4mPP94TDUS4Us'
    ]
    for url in user_url_list:
        try:
            profile.save_profile_info(url)
        except:
            print(f'user {url} 查询失败')


if __name__ == '__main__':
    main()
