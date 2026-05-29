import hashlib
import json

import websocket
from websocket import WebSocketApp

try:
    from dy_apis.douyin_api import DouyinAPI
except ImportError:
    from douyin_api import DouyinAPI
from builder.auth import DouyinAuth
from builder.header import HeaderBuilder
from builder.params import Params
from static import Live_pb2, Response_pb2


class DouyinRecvMsg:
    appKey = "e1bd35ec9db7b8d846de66ed140b1ad9"
    fpId = '9'

    def __init__(self, auth: DouyinAuth, auto_reconnect=True, event_sink=None, error_sink=None, close_sink=None):
        self.auto_reconnect = auto_reconnect
        self.event_sink = event_sink
        self.error_sink = error_sink
        self.close_sink = close_sink
        self._stopped = False
        self.auth = auth
        self.ws = None
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

    def emit(self, payload):
        if self.event_sink:
            self.event_sink(payload)
            return
        print(payload)

    def stop(self):
        self._stopped = True
        if self.ws:
            self.ws.close()

    def on_open(self, ws):
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
                self.emit({
                    "event_type": "text",
                    "conversation_id": conversation_id,
                    "index": index,
                    "sender": sender,
                    "content": content["text"],
                })
            elif msg_type == 5:
                self.emit({
                    "event_type": "emoji",
                    "conversation_id": conversation_id,
                    "index": index,
                    "sender": sender,
                    "content": content["url"]["url_list"][0],
                })
            elif msg_type == 17:
                self.emit({
                    "event_type": "voice",
                    "conversation_id": conversation_id,
                    "index": index,
                    "sender": sender,
                    "content": content["resource_url"]["url_list"][0],
                })
            elif msg_type == 27:
                self.emit({
                    "event_type": "image",
                    "conversation_id": conversation_id,
                    "index": index,
                    "sender": sender,
                    "content": content["resource_url"]["origin_url_list"][0],
                })
            elif msg_type == 8:
                self.emit({
                    "event_type": "share",
                    "conversation_id": conversation_id,
                    "index": index,
                    "sender": sender,
                    "content": content["itemId"],
                })
            elif msg_type == 50001:
                self.emit({
                    "event_type": "read",
                    "conversation_id": conversation_id,
                    "index": index,
                    "sender": sender,
                    "content": content["read_index"],
                })
        elif frame.payloadType == 'text/json':
            self.emit(json.loads(frame.payload))

    def on_error(self, ws, error):
        if self.error_sink:
            self.error_sink(error)
        else:
            print("\033[31m### error ###")
            print(error)
            print("### ===error=== ###\033[m")
        if (
            isinstance(error, ConnectionRefusedError)
            or isinstance(error, websocket._exceptions.WebSocketConnectionClosedException)
        ) and self.auto_reconnect and not self._stopped:
            self.start()

    def on_close(self, ws, close_status_code, close_msg):
        if self.close_sink:
            self.close_sink({"status_code": close_status_code, "message": close_msg})
        else:
            print("\033[31m### closed ###")
            print(f"status_code: {close_status_code}, msg: {close_msg}")
            print("### ===closed=== ###\033[m")

    def start(self):
        self.ws = WebSocketApp(
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
        try:
            self.ws.run_forever(origin='https://www.douyin.com')
        except KeyboardInterrupt:
            self.ws.close()
        except:
            self.ws.close()


if __name__ == '__main__':
    # websocket.enableTrace(True)
    web_protect_str = r''
    keys_str = r''
    cookies_str = r''
    auth_ = DouyinAuth()
    auth_.perepare_auth(cookies_str, web_protect_str, keys_str)
    douyinMsg = DouyinRecvMsg(auth_)
    douyinMsg.start()
