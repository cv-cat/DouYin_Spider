import asyncio
import getpass
import os
import re

import aiofiles
from playwright.async_api import async_playwright
from urllib.parse import urlparse

def check_path(path):
    if not os.path.exists(path):
        return False
    return True
def get_socket_template():
    return """
            const socket_dy = new WebSocket('ws://localhost:port');
            socket_dy.onopen = (event) => {
                console.log('WebSocket connection opened:', event);
            };
            
            socket_dy.onmessage = (event) => {
                console.log('Received message:', event.data);
            };
            
            socket_dy.onclose = (event) => {
                console.log('WebSocket connection closed:', event);
            };
            
            function sendMessage(res_dy) {
                socket_dy.send(JSON.stringify(res_dy));
            };
            """

def get_emit_template():
    return """
            ,window.res_dy = replacement,
                !function () {
                    if(typeof(t[0]) == "string"){
                        return
                    }
                    console.log(window.res_dy);
                    if(e == "#sync#ChatMessage" || e== "#sync#GiftMessage"){
                        sendMessage(window.res_dy)
                    }
                }()
            """

js_dict = None
pattern = re.compile('null==\(r=this\._debug\)\|\|r\.call\(this,e,\.\.\.(.*?)\),this')
async def handle_response(response):
    url = response.url
    if url.endswith('.js'):
        js_text = await response.text()
        if 'emit_error' in js_text:
            js_name = urlparse(url).path.split('/')[-1]
            variable = re.findall(pattern, js_text)[0]
            replacement = re.search(pattern, js_text).group()
            emit_template = get_emit_template()
            insert = emit_template.replace('replacement', variable)
            insert = replacement + insert
            js_text = js_text.replace(replacement, insert)
            global js_dict
            js_dict = {
                'name': js_name,
                'text': js_text
            }
async def check_js():
    while True:
        if js_dict is not None:
            break
        await asyncio.sleep(1)

async def getJS():
    url = 'https://live.douyin.com/567973675942'
    USER_DIR_PATH = f"C:\\Users\\{getpass.getuser()}\\AppData\Local\Google\Chrome\\User Data"
    headless = True
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DIR_PATH,
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
            ],
            channel='chrome'
        )
        page = await browser.new_page()
        page.on("response", lambda request: handle_response(response=request))
        await page.goto(url)
        await check_js()
        await browser.close()

async def get_new_JS(port=9999):
    await getJS()
    socket_template = get_socket_template()
    socket_template = socket_template.replace('port', str(port))
    js_dict['text'] = socket_template + js_dict['text']
    return js_dict

async def save_new_JS(port=9999):
    js_dict = await get_new_JS(port)
    path = f'./static/{js_dict["name"]}'
    exist = check_path(path)
    if not exist:
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(js_dict['text'])
        print(f'抖音JS文件更新，已保存到{path}')
    else:
        print(f'抖音JS文件无需更新')
    return js_dict["name"], path

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(save_new_JS())

