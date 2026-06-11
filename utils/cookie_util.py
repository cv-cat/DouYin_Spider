from urllib.parse import urlparse, parse_qs
import asyncio

from playwright.async_api import async_playwright

webid = None
msToken = None
cookies = None


def _cookies_to_str(cookie_dict):
    return "; ".join([f"{key}={value}" for key, value in cookie_dict.items() if key])


def handle_request(request):
    url = request.url
    if url.startswith('https://www.douyin.com/aweme/v1/web/user/profile/other/'):
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        global webid
        webid = query_params.get('webid', [None])[0]

# 每隔1秒判断webid是否拿到
async def check_webid(timeout=30):
    for _ in range(timeout):
        if webid is not None:
            return
        await asyncio.sleep(1)
    raise TimeoutError("未捕获到 user/profile/other 请求里的 webid")


async def get_ttwid_and_webid(
        url='https://www.douyin.com/user/MS4wLjABAAAAEpmH344CkCw2M58T33Q8TuFpdvJsOyaZcbWxAMc6H03wOVFf1Ow4mPP94TDUS4Us',
        headless=False,
        timeout=30,
):
    global webid, msToken, cookies
    webid = None
    msToken = None
    cookies = None
    print('如出现验证过程，请手动验证')
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
            ],
            channel='chrome'
        )
        page = await browser.new_page()
        page.on("request", lambda request: handle_request(request=request))
        await page.goto(url)
        await asyncio.sleep(3)
        await check_webid(timeout=timeout)
        page_cookies = await page.context.cookies()
        await browser.close()
        cookies = {}
        for cookie in page_cookies:
            if not cookie.get('name'):
                continue
            cookies[cookie['name']] = cookie['value']
            if cookie['name'] == 'msToken':
                msToken = cookie['value']
        if webid and 's_v_web_id' not in cookies:
            cookies['s_v_web_id'] = webid


def get_new_cookies(url=None, headless=False, timeout=30):
    kwargs = {"headless": headless, "timeout": timeout}
    if url:
        kwargs["url"] = url
    asyncio.run(get_ttwid_and_webid(**kwargs))
    return {
        'webid': webid,
        'msToken': msToken,
        'cookies': cookies,
        'cookie_str': _cookies_to_str(cookies),
    }

if __name__ == '__main__':
    print(get_new_cookies())
