import asyncio
import json

import argparse
import websockets


class Server():
    def __init__(self, port=9999):
        self.port = port
        self.client_list = []
        self.user_homepage_url = 'https://www.douyin.com/user/'

    async def handle_client(self, websocket, path):
        print(f"Client connected: {websocket}")
        self.client_list.append({
            'websocket': websocket,
            'path': path
        })
        try:
            while True:
                resv_text = await websocket.recv()
                res = json.loads(resv_text)
                paload = res[0]['payload']
                nickname = paload['user']['nickname']
                pay_grade_level = paload['user']['pay_grade']['level']
                sec_uid = paload['user']['sec_uid']
                if res[0]['method'] == 'WebcastChatMessage':
                    content = paload['content']
                    print(f'【弹幕信息】 用户:【{nickname}】 等级{pay_grade_level} 说了 【{content}】, home_url: {self.user_homepage_url + sec_uid} ')
                elif res[0]['method'] == 'WebcastGiftMessage':
                    gift_name = paload['gift']['name']
                    print(f'【礼物信息】 用户:【{nickname}】 等级{pay_grade_level} 送出了 【{gift_name}】!! home_url: {self.user_homepage_url + sec_uid} ')

        except:
            print(f"Client disconnected: {websocket}")
            self.client_list.remove({
                'websocket': websocket,
                'path': path
            })


    def main(self,):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        start_server = websockets.serve(self.handle_client, "localhost", self.port)
        print(f'服务已经启动，端口：{self.port}')
        loop.run_until_complete(start_server)
        loop.run_forever()

def parse_args():
    description = "你可以调整端口传递port字段"
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--port', type=int, help='port', default=9999)
    args = parser.parse_args()
    return args

# python .\server.py --port 10101
if __name__ == '__main__':
    args = parse_args()
    port = args.port
    server = Server(port=port)
    server.main()
