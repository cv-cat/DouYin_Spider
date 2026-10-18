import hashlib
import json
import threading
import time

import websocket
from websocket import WebSocketApp

from dy_apis.douyin_api import DouyinAPI
from builder.auth import DouyinAuth
from builder.header import HeaderBuilder
from builder.params import Params
from static import Live_pb2, Response_pb2


class DouyinRecvMsg:
    appKey = "e1bd35ec9db7b8d846de66ed140b1ad9"
    fpId = '9'

    # 重连退避：1 秒起，指数增长，上限 30 秒
    RECONNECT_BACKOFF_START = 1.0
    RECONNECT_BACKOFF_MAX = 30.0

    def __init__(self, auth: DouyinAuth, auto_reconnect=True):
        self.auto_reconnect = auto_reconnect
        self.auth = auth
        self.ws = None
        self._should_reconnect = False   # on_error 打标记，真正重连在 start() 的循环里
        self._stopped = False            # stop() 置位，用来跳出重连循环
        self._stop_event = threading.Event()
        self._opened = False             # 本轮连接是否成功建立过（用来重置退避）
        deviceId = DouyinAPI.get_device_id(auth=self.auth)
        accessKey = f'{self.fpId + self.appKey + deviceId}f8a69f1719916z'
        accessKey = hashlib.md5(accessKey.encode(encoding='UTF-8')).hexdigest()
        params = Params()
        (params
         .add_param("aid", "6383")
         .add_param("device_platform", "douyin_pc")
         .add_param("fpid", self.fpId)
         .add_param("device_id", deviceId)
         .add_param("token", self.auth.cookie["sessionid"])
         .add_param("access_key", accessKey)
         )
        self.url = f"wss://frontier-im.douyin.com/ws/v2?{params.toString()}"

    def on_open(self, ws):
        self._opened = True
        print("WebSocket connection open.")

    def on_message(self, ws, message):
        frame = Live_pb2.PushFrame()
        frame.ParseFromString(message)
        if frame.payloadType == 'pb':
            response = Response_pb2.Response()
            response.ParseFromString(frame.payload)
            sender = response.body.new_message_notify.message.sender
            content = response.body.new_message_notify.message.content
            msg_type = response.body.new_message_notify.message.message_type
            conversation_id = response.body.new_message_notify.message.conversation_id
            index = response.body.new_message_notify.message.index_in_conversation
            content = json.loads(content)
            if msg_type == 7:
                print(f'【消息编号:{index}】【聊天室ID:{conversation_id}】【来自:{sender}】文本消息:{content["text"]}')
            elif msg_type == 5:
                print(f'【消息编号:{index}】【聊天室ID:{conversation_id}】【来自:{sender}】用户表情包消息:{content["url"]["url_list"][0]}')
            elif msg_type == 17:
                print(f'【消息编号:{index}】【聊天室ID:{conversation_id}】【来自:{sender}】语音信息:{content["resource_url"]["url_list"][0]}')
            elif msg_type == 27:
                print(f'【消息编号:{index}】【聊天室ID:{conversation_id}】【来自:{sender}】图片信息:{content["resource_url"]["origin_url_list"][0]}')
            elif msg_type == 8:
                print(f'【消息编号:{index}】【聊天室ID:{conversation_id}】【来自:{sender}】分享视频信息:视频ID{content["itemId"]}')
            elif msg_type == 50001:
                print(f'对方已读，消息标号:{content["read_index"]}')
        elif frame.payloadType == 'text/json':
            print(json.loads(frame.payload))

    def on_error(self, ws, error):
        print("\033[31m### error ###")
        print(error)
        print("### ===error=== ###\033[m")
        # 原写法是 `A or B and self.auto_reconnect`，按优先级等于 `A or (B and ...)`，
        # 于是 ConnectionRefusedError 会绕过 auto_reconnect 开关无条件重连。
        # 另外用 type()== 判断会漏掉子类，改 isinstance。
        if not self.auto_reconnect:
            return
        if isinstance(error, (ConnectionRefusedError,
                              websocket.WebSocketConnectionClosedException)):
            # 这里只打标记。以前是直接调 self.start()，而 start() 内部是阻塞的
            # run_forever —— 每次重连都往调用栈上再压一层，不是循环，
            # 断线次数多了栈会一直涨直到 RecursionError。真正的重连交给 start()。
            self._should_reconnect = True

    def on_close(self, ws, close_status_code, close_msg):
        print("\033[31m### closed ###")
        print(f"status_code: {close_status_code}, msg: {close_msg}")
        print("### ===closed=== ###\033[m")

    def stop(self):
        """外部主动停止：关掉当前连接并让 start() 的重连循环退出。"""
        self._stopped = True
        self.auto_reconnect = False
        self._stop_event.set()
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass

    def _new_ws(self):
        return WebSocketApp(
            url=self.url,
            header={
                'Pragma': 'no-cache',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                'User-Agent': HeaderBuilder.ua,
                'Cache-Control': 'no-cache',
                'Sec-WebSocket-Protocol': 'binary, base64, pbbp2',
                'Sec-WebSocket-Extensions': 'permessage-deflate; client_max_window_bits'
            },
            cookie=self.auth.cookie_str,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )

    def start(self):
        """阻塞运行；断线按退避重连。重连是**循环**，不是递归压栈。"""
        backoff = self.RECONNECT_BACKOFF_START
        while not self._stopped:
            self._should_reconnect = False
            self._opened = False
            self.ws = self._new_ws()
            try:
                self.ws.run_forever(origin='https://www.douyin.com')
            except KeyboardInterrupt:
                self.ws.close()
                break
            except Exception as e:
                print(f"\033[31m### run_forever 异常: {type(e).__name__}: {e} ###\033[m")
                try:
                    self.ws.close()
                except Exception:
                    pass
            if self._stopped or not (self.auto_reconnect and self._should_reconnect):
                break
            if self._opened:
                # 这轮连上过，说明不是持续性故障，退避重置
                backoff = self.RECONNECT_BACKOFF_START
            print(f"\033[33m### {backoff:.0f} 秒后重连 ###\033[m")
            try:
                if self._stop_event.wait(backoff):
                    break
            except KeyboardInterrupt:
                break
            backoff = min(backoff * 2, self.RECONNECT_BACKOFF_MAX)


if __name__ == '__main__':
    # websocket.enableTrace(True)
    web_protect_str = r''
    keys_str = r''
    cookies_str = r''
    auth_ = DouyinAuth()
    auth_.perepare_auth(cookies_str, web_protect_str, keys_str)
    douyinMsg = DouyinRecvMsg(auth_)
    douyinMsg.start()
