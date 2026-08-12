"""私信接收桥:复用 SDK DouyinRecvMsg 的连接逻辑,事件转发到 event_bus。"""
import hashlib
import json
import threading

from webapp.backend.eventbus import event_bus


class MsgBridge:
    appKey = "e1bd35ec9db7b8d846de66ed140b1ad9"
    fpId = "9"

    def __init__(self, auth):
        from urllib.parse import urlencode
        from dy_apis.douyin_api import DouyinAPI
        from builder.params import Params

        self.auth = auth
        self.ws = None
        self._stopping = False
        self._thread = None

        device_id = DouyinAPI.get_device_id(auth=auth)
        access_key = f"{self.fpId + self.appKey + device_id}f8a69f1719916z"
        access_key = hashlib.md5(access_key.encode("UTF-8")).hexdigest()
        params = Params()
        (params.add_param("aid", "6383").add_param("device_platform", "douyin_pc")
         .add_param("fpid", self.fpId).add_param("device_id", device_id)
         .add_param("token", auth.cookie["sessionid"]).add_param("access_key", access_key))
        self.url = f"wss://frontier-im.douyin.com/ws/v2?{params.toString()}"

    def on_open(self, ws):
        event_bus.publish("messages", {"type": "msg.status", "data": {"state": "open"}})

    def on_message(self, ws, message):
        from static import Live_pb2, Response_pb2
        try:
            frame = Live_pb2.PushFrame()
            frame.ParseFromString(message)
            if frame.payloadType == "pb":
                response = Response_pb2.Response()
                response.ParseFromString(frame.payload)
                notify = response.body.new_message_notify.message
                sender = notify.sender
                content_raw = notify.content
                msg_type = notify.message_type
                conversation_id = notify.conversation_id
                index = notify.index_in_conversation
                try:
                    content = json.loads(content_raw)
                except Exception:
                    content = {"raw": content_raw}
                base = {"index": index, "conversation_id": conversation_id,
                        "sender": sender, "msg_type": msg_type}
                if msg_type == 7:
                    self._publish("msg.text", {**base, "text": content.get("text", "")})
                elif msg_type == 5:
                    url = content.get("url", {}).get("url_list", [""])[0]
                    self._publish("msg.emoji", {**base, "url": url})
                elif msg_type == 17:
                    url = content.get("resource_url", {}).get("url_list", [""])[0]
                    self._publish("msg.voice", {**base, "url": url})
                elif msg_type == 27:
                    urls = content.get("resource_url", {}).get("origin_url_list", [""])
                    self._publish("msg.image", {**base, "url": urls[0] if urls else ""})
                elif msg_type == 8:
                    self._publish("msg.video", {**base, "item_id": content.get("itemId")})
                elif msg_type == 50001:
                    self._publish("msg.read", {**base, "read_index": content.get("read_index")})
                else:
                    self._publish("msg.raw", {**base, "content": content})
            elif frame.payloadType == "text/json":
                try:
                    data = json.loads(frame.payload)
                except Exception:
                    data = {"raw": frame.payload.decode("utf-8", errors="replace")}
                self._publish("msg.raw", {"payload": data})
        except Exception as e:
            self._publish("msg.status", {"state": "error", "detail": str(e)})

    def on_error(self, ws, error):
        self._publish("msg.status", {"state": "error", "detail": str(error)})
        if not self._stopping:
            try:
                self.start()
            except Exception:
                pass

    def on_close(self, ws, close_status_code, close_msg):
        self._publish("msg.status", {"state": "close", "code": close_status_code, "msg": close_msg})

    def start(self):
        from websocket import WebSocketApp
        from builder.header import HeaderBuilder
        self._stopping = False
        self.ws = WebSocketApp(
            url=self.url,
            header={"Pragma": "no-cache", "Accept-Language": "zh-CN,zh;q=0.9",
                    "User-Agent": HeaderBuilder.ua, "Cache-Control": "no-cache",
                    "Sec-WebSocket-Protocol": "binary, base64, pbbp2",
                    "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits"},
            cookie=self.auth.cookie_str,
            on_message=self.on_message, on_error=self.on_error,
            on_close=self.on_close, on_open=self.on_open,
        )
        self._thread = threading.Thread(
            target=lambda: self.ws.run_forever(origin="https://www.douyin.com"), daemon=True)
        self._thread.start()

    def stop(self):
        self._stopping = True
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _publish(self, evt_type: str, data: dict):
        event_bus.publish("messages", {"type": evt_type, "data": data})
