from builder.header import HeaderBuilder
from utils.fingerprint import get_profile
from utils.dy_util import generate_webid, generate_msToken, splice_url, generate_a_bogus, generate_fake_webid


class Params:
    def __init__(self):
        self.params = {}

    def with_platform(self, round_trip_time='0', auth=None, url="",
                      uifid=True, verify_fp=True,
                      version_code='170400', version_name='17.4.0'):
        """www.douyin.com 的公共 query 组。

        字段与顺序按浏览器实测（2026-08-15）对齐：`pc_client_type` 后面紧跟
        `pc_libra_divert` / `support_h265` / `support_dash` / `cpu_core_num`，
        `device_memory` 挪到 `os_version` 之后。缺这几个会被部分接口静默拒绝。

        传了 `auth` 就顺带把 `webid` / `uifid` / `verifyFp` / `fp` 也补上 ——
        2026-08-16 抓 44 个主站接口统计，这四个的出现率分别是
        44/44、41/44、43/44、43/44，属于公共参数；以前要各接口自己记得调
        `with_web_id()` / `with_uifid()`，漏掉的就少字段。顺序照实录：
        `round_trip_time` 之后依次 webid、uifid、verifyFp、fp。

        个别接口确实不带其中某项时，用 `uifid=False` / `verify_fp=False`
        关掉，**依据必须是该接口的抓包**。当前 PC Web 的 comment/list 和
        comment/list/reply 都带 uifid。

        `round_trip_time` 默认 0：44 个接口里的主流取值，以前默认 50 是错的。
        """
        params = {
            'device_platform': 'webapp',
            'aid': '6383',
            'channel': 'channel_pc_web',
            'update_version_code': '170400',
            'pc_client_type': '1',
            'pc_libra_divert': 'Windows',
            'support_h265': '1',
            'support_dash': '1',
            'cpu_core_num': get_profile()["cpu_core_num"],
            'version_code': version_code,
            'version_name': version_name,
            'cookie_enabled': 'true',
            'screen_width': get_profile()["screen_width"],
            'screen_height': get_profile()["screen_height"],
            'browser_language': 'zh-CN',
            'browser_platform': 'Win32',
            'browser_name': get_profile()["browser_name"],
            'browser_version': get_profile()["browser_version"],
            'browser_online': 'true',
            'engine_name': 'Blink',
            'engine_version': get_profile()["engine_version"],
            'os_name': 'Windows',
            'os_version': '10',
            'device_memory': get_profile()["device_memory"],
            'platform': 'PC',
            'downlink': '10',
            'effective_type': '4g',
            'round_trip_time': round_trip_time,
        }
        self.params.update(params)
        if auth is not None:
            self.with_web_id(auth, url)
            if uifid:
                self.with_uifid(auth)
            if verify_fp:
                self.with_verify_fp(auth)
        return self

    def with_uifid(self, auth):
        """uifid 取自 UIFID Cookie，位置紧跟 webid。"""
        uifid = (auth.cookie or {}).get('UIFID', '') if auth else ''
        if uifid:
            self.params['uifid'] = uifid
        return self

    def with_verify_fp(self, auth):
        """verifyFp / fp 都取 s_v_web_id。注意不同接口相对 a_bogus 的位置不同。"""
        fp = (auth.cookie or {}).get('s_v_web_id', '')
        if fp:
            self.params['verifyFp'] = fp
            self.params['fp'] = fp
        return self

    def with_live_platform(self, round_trip_time='50'):
        """live.douyin.com 上电商类接口的公共 query 组。

        照 2026-08-17 `/live/promotions/pop/v3/` 的浏览器实录，与主站
        `with_platform()` 有四处不同，**不要为了统一而抹掉**：

        - `version_code` / `version_name` 是直播 SDK 的 `320100` / `32.1.0`
          （主站那批是 `170400` / `17.4.0`）
        - `support_dash` 是 `0`（主站是 `1`）
        - `round_trip_time` 实录是 `50`（主站是 `0`）
        - `cpu_core_num` 紧跟 `support_dash`，而主站是排在 `os_version` 之后
        """
        params = {
            'update_version_code': '170400',
            'pc_client_type': '1',
            'pc_libra_divert': 'Windows',
            'support_h265': '1',
            'support_dash': '0',
            'cpu_core_num': get_profile()["cpu_core_num"],
            'version_code': '320100',
            'version_name': '32.1.0',
            'cookie_enabled': 'true',
            'screen_width': get_profile()["screen_width"],
            'screen_height': get_profile()["screen_height"],
            'browser_language': 'zh-CN',
            'browser_platform': 'Win32',
            'browser_name': get_profile()["browser_name"],
            'browser_version': get_profile()["browser_version"],
            'browser_online': 'true',
            'engine_name': 'Blink',
            'engine_version': get_profile()["engine_version"],
            'os_name': 'Windows',
            'os_version': '10',
            'device_memory': get_profile()["device_memory"],
            'platform': 'PC',
            'downlink': '10',
            'effective_type': '4g',
            'round_trip_time': round_trip_time,
        }
        self.params.update(params)
        return self

    def with_creator_platform(self):
        """创作者中心（creator.douyin.com）接口的固定 query 组。

        实测抓包（2026-08-15）：browser_name=Mozilla、browser_version 取 navigator.appVersion
        （即 UA 去掉 "Mozilla/" 前缀）、aid=1128、带 timezone_name / support_h265，
        不带 device_platform / channel。
        """
        params = {
            'cookie_enabled': 'true',
            'screen_width': get_profile()["screen_width"],
            'screen_height': get_profile()["screen_height"],
            'browser_language': 'zh-CN',
            'browser_platform': 'Win32',
            'browser_name': 'Mozilla',
            'browser_version': get_profile()["ua"].replace('Mozilla/', '', 1),
            'browser_online': 'true',
            'timezone_name': 'Asia/Shanghai',
            'aid': '1128',
            'support_h265': '1',
        }
        self.params.update(params)
        return self

    def update_params(self, params):
        self.params.update(params)
        return self

    def with_web_id(self, auth=None, url="", fake=False):
        # 走 auth.webid 而不是按 url 现抓：调用方传进来的页面常常是客户端渲染的，
        # 抓不到 user_unique_id 就会退化成随机数，被接口静默拒绝
        if fake or auth is None:
            webid = generate_fake_webid()
        else:
            webid = auth.webid or generate_webid(auth, url)
        self.params['webid'] = webid
        return self

    def with_a_bogus(self, data=None, host='www.douyin.com'):
        """算 a_bogus。host 必须是本次请求的子域：签名里内嵌 (aid, page_id)，
        www / live / creator 三套值不同，用错了强校验接口会判人机验证。
        """
        query = splice_url(self.get())
        if data is not None:
            data = splice_url(data)
        else:
            data = ''
        abogus = generate_a_bogus(query, data, host=host)
        self.add_param('a_bogus', abogus)
        return self

    def with_ms_token(self):
        msToken = generate_msToken()
        self.params['msToken'] = msToken
        return self

    def signed_url(self, base_url, auth=None, ts=None):
        """把参数拼成带 `timestamp` + `x-secsdk-web-signature` 的完整 URL。

        只有 secsdk 的 webSign 策略覆盖的接口才需要（见
        `utils/secsdk_web_sign.PROTECTED_PATHS_GET`）。签名是对**规范化后的
        query** 算的，服务端也按收到的 query 校验，所以必须发这里返回的 URL，
        不能再把 `self.get()` 当 params 传给 requests——那样 query 会被重新
        编码一遍，与签名输入对不上。

        用法：
            url = params.signed_url(f'{DouyinAPI.douyin_url}{api}', auth)
            resp = requests.get(url, headers=..., cookies=...)   # 不传 params
        """
        from utils.secsdk_web_sign import sign_url
        uifid = (auth.cookie or {}).get('UIFID', '') if auth else ''
        return sign_url(base_url + '?' + self.toString(), ts=ts, uifid=uifid)

    def add_param(self, key, value):
        self.params[key] = value
        return self

    def get(self):
        return self.params

    def sort(self):
        order = ['device_platform', 'aid', 'channel', 'publish_video_strategy_type', 'source', 'sec_user_id',
                 'personal_center_strategy', 'update_version_code', 'pc_client_type', 'version_code', 'version_name',
                 'cookie_enabled', 'screen_width', 'screen_height', 'browser_language', 'browser_platform',
                 'browser_name', 'browser_version', 'browser_online', 'engine_name', 'engine_version', 'os_name',
                 'os_version', 'cpu_core_num', 'device_memory', 'platform', 'downlink', 'effective_type',
                 'round_trip_time', 'webid', 'verifyFp', 'fp', 'msToken', 'a_bogus']
        # 按照 order 排序的字段
        sorted_params = {key: self.params[key] for key in order if key in self.params}
        # 不在 order 中的字段
        remaining_params = {key: self.params[key] for key in self.params if key not in order}
        # 合并两个字典
        sorted_params.update(remaining_params)
        self.params = sorted_params

    def toString(self):
        # 按url参数格式拼接参数
        return "&".join([f"{k}={v}" for k, v in self.params.items()])
