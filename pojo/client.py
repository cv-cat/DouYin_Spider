import asyncio
import getpass

import argparse

from dy_utils.zb_util import save_new_JS
from playwright.async_api import async_playwright

class Client():
    def __init__(self, url, headless=True, port=9999):
        self.url = url
        self.headless = headless
        self.port = port
        self.dy_js_url = 'https://lf-cdn-tos.bytescm.com/obj/static/webcast/douyin_live'

    async def get_cookies(self,):
        async with async_playwright() as p:
            USER_DIR_PATH = f"C:\\Users\\{getpass.getuser()}\\AppData\Local\Google\Chrome\\User Data"
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=USER_DIR_PATH,
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                ],
                channel='chrome'
            )
            page = await browser.new_page()
            await page.goto(url)
            page_cookies = await page.context.cookies()
            await browser.close()
            return page_cookies

    async def open_page(self,):
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                ],
                channel='chrome'
            )
            page = await browser.new_page()
            cookies = await self.get_cookies()
            await page.context.add_cookies(cookies)
            js_name, path = await save_new_JS(self.port)
            await page.route(
                f'{self.dy_js_url}/{js_name}',
                lambda route: route.fulfill(path=path)
            )
            await page.goto(url)
            while 1:
                pass

    def main(self,):
        asyncio.get_event_loop().run_until_complete(self.open_page())

def parse_args():
    description = "你可以调整端口传递url字段和port字段和headless字段"
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--url', type=str, help='url', default='https://live.douyin.com/31267501116')
    parser.add_argument('--port', type=int, help='port', default=9999)
    args = parser.parse_args()
    return args

# python .\client.py --url https://live.douyin.com/31267501116 --port 10101
if __name__ == '__main__':
    args = parse_args()
    url = args.url
    port = args.port
    # url = 'https://live.douyin.com/31267501116'
    client = Client(url=url, port=9999, headless=True)
    client.main()
