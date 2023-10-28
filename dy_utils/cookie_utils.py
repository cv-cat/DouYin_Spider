import asyncio
import getpass
from playwright.async_api import async_playwright
from urllib.parse import urlparse, parse_qs

webid = None
msToken = None
cookies = None
def handle_request(request):
    url = request.url
    if url.startswith('https://www.douyin.com/aweme/v1/web/user/profile/other/'):
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        global webid
        webid = query_params['webid'][0]

# 每隔1秒判断webid是否拿到
async def check_webid():
    while True:
        if webid is not None:
            break
        await asyncio.sleep(1)

async def get_ttwid_and_webid():
    domian_key = ['douyin', 'bytedance']
    url = 'https://www.douyin.com/user/MS4wLjABAAAAEpmH344CkCw2M58T33Q8TuFpdvJsOyaZcbWxAMc6H03wOVFf1Ow4mPP94TDUS4Us'
    USER_DIR_PATH = f"C:\\Users\\{getpass.getuser()}\\AppData\Local\Google\Chrome\\User Data"
    headless = False
    print('如出现验证过程，请手动验证')
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DIR_PATH,
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
            ],
            channel='chrome'
        )
        page = browser.pages[0]
        page.on("request", lambda request: handle_request(request=request))
        page_cookies = await page.context.cookies()
        await page.goto(url)
        await check_webid()
        await browser.close()
        await asyncio.sleep(3)
        global cookies
        cookies = {}
        for cookie in page_cookies:
            for key in domian_key:
                if key in cookie['domain']:
                    cookies[cookie['name']] = cookie['value']
                    if cookie['name'] == 'msToken':
                        global msToken
                        msToken = cookie['value']
                    break





def get_new_cookies():
    asyncio.run(get_ttwid_and_webid())
    return {
        'webid': webid,
        'msToken': msToken,
        'cookies': cookies,
    }

if __name__ == '__main__':
    print(get_new_cookies())

