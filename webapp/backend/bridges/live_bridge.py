"""直播桥:子类化 SDK DouyinLive,把 on_message 事件转发到 event_bus。"""
import gzip
import threading

from webapp.backend.eventbus import event_bus


class LiveBridge:
    """独立实现,复用 SDK 的连接逻辑,事件发布到 event_bus 频道 live:{room_id}。
    不直接 import dy_live.server.DouyinLive(其 on_message 只 print),这里重写解码+发布。"""

    def __init__(self, live_id: str, auth_):
        self.auth_ = auth_
        self.live_id = live_id
        self.ws = None
        self._stopping = False
        self._thread = None

    # ----- WebSocket 回调 -----
    def ping(self, ws):
        import time
        from static import Live_pb2
        while True:
            frame = Live_pb2.PushFrame()
            frame.payloadType = "hb"
            try:
                ws.send(frame.SerializeToString(), opcode=0x02)
                time.sleep(5)
            except Exception:
                ws.close()
                break

    def on_open(self, ws):
        threading.Thread(target=self.ping, args=(ws,), daemon=True).start()
        self._publish("live.status", {"state": "open"})

    def on_message(self, ws, message):
        from static import Live_pb2
        try:
            frame = Live_pb2.PushFrame()
            frame.ParseFromString(message)
            payload = gzip.decompress(frame.payload)
            response = Live_pb2.LiveResponse()
            response.ParseFromString(payload)
            if response.needAck:
                s = Live_pb2.PushFrame()
                s.payloadType = "ack"
                s.payload = response.internalExt.encode("utf-8")
                s.logId = frame.logId
                ws.send(s.SerializeToString(), opcode=0x02)
            for item in response.messagesList:
                method = item.method
                msg = None
                try:
                    if method == "WebcastGiftMessage":
                        msg = Live_pb2.GiftMessage()
                        msg.ParseFromString(item.payload)
                        self._publish("live.gift", {
                            "sec_uid": msg.user.sec_uid, "nickname": msg.user.nickname,
                            "to_sec_uid": msg.toUser.sec_uid, "to_nickname": msg.toUser.nickname,
                            "gift_name": msg.gift.name, "combo_count": msg.comboCount,
                        })
                    elif method == "WebcastChatMessage":
                        msg = Live_pb2.ChatMessage()
                        msg.ParseFromString(item.payload)
                        self._publish("live.chat", {
                            "sec_uid": msg.user.sec_uid, "nickname": msg.user.nickname,
                            "content": msg.content,
                        })
                    elif method == "WebcastMemberMessage":
                        msg = Live_pb2.MemberMessage()
                        msg.ParseFromString(item.payload)
                        self._publish("live.member", {
                            "sec_uid": msg.user.sec_uid, "nickname": msg.user.nickname,
                        })
                    elif method == "WebcastLikeMessage":
                        msg = Live_pb2.LikeMessage()
                        msg.ParseFromString(item.payload)
                        self._publish("live.like", {
                            "sec_uid": msg.user.sec_uid, "nickname": msg.user.nickname,
                            "count": msg.count, "total": msg.total,
                        })
                    elif method == "WebcastSocialMessage":
                        msg = Live_pb2.SocialMessage()
                        msg.ParseFromString(item.payload)
                        self._publish("live.social", {
                            "sec_uid": msg.user.sec_uid, "nickname": msg.user.nickname,
                            "action": msg.action,
                        })
                    elif method == "WebcastRoomStatsMessage":
                        msg = Live_pb2.RoomStatsMessage()
                        msg.ParseFromString(item.payload)
                        self._publish("live.room_stats", {"display_long": msg.displayLong})
                except Exception:
                    continue
        except Exception as e:
            self._publish("live.status", {"state": "error", "detail": str(e)})

    def on_error(self, ws, error):
        self._publish("live.status", {"state": "error", "detail": str(error)})

    def on_close(self, ws, close_status_code, close_msg):
        self._publish("live.status", {"state": "close",
                                      "code": close_status_code, "msg": close_msg})
        if not self._stopping:
            # 断线重连(直播间仍开着)
            try:
                self._start_ws()
            except Exception:
                pass

    # ----- 连接 -----
    def _start_ws(self):
        from urllib.parse import urlencode
        from websocket import WebSocketApp
        from dy_apis.douyin_api import DouyinAPI
        from builder.header import HeaderBuilder
        from builder.params import Params
        from utils.dy_util import generate_signature
        from static import Live_pb2

        room_info = DouyinAPI.get_live_info(self.auth_, self.live_id)
        room_id = room_info["room_id"]
        user_id = room_info["user_id"]
        params = Params()
        res = DouyinAPI.get_webcast_detail(self.auth_, str(user_id), room_id,
                                           f"https://live.douyin.com/{self.live_id}")
        frame = Live_pb2.LiveResponse()
        frame.ParseFromString(res)
        (params
         .add_param("app_name", "douyin_web").add_param("version_code", "180800")
         .add_param("webcast_sdk_version", "1.0.15").add_param("update_version_code", "1.0.15")
         .add_param("compress", "gzip").add_param("device_platform", "web")
         .add_param("cookie_enabled", "true").add_param("screen_width", "1707")
         .add_param("screen_height", "960").add_param("browser_language", "zh-CN")
         .add_param("browser_platform", "Win32").add_param("browser_name", "Mozilla")
         .add_param("browser_version", HeaderBuilder.ua.split("Mozilla/")[-1])
         .add_param("browser_online", "true").add_param("tz_name", "Etc/GMT-8")
         .add_param("cursor", str(frame.cursor)).add_param("internal_ext", frame.internalExt)
         .add_param("host", "https://live.douyin.com").add_param("aid", "6383")
         .add_param("live_id", "1").add_param("did_rule", "3").add_param("endpoint", "live_pc")
         .add_param("support_wrds", "1").add_param("user_unique_id", str(user_id))
         .add_param("im_path", "/webcast/im/fetch/").add_param("identity", "audience")
         .add_param("need_persist_msg_count", "15").add_param("insert_task_id", "")
         .add_param("live_reason", "").add_param("room_id", room_id)
         .add_param("heartbeatDuration", "0")
         .add_param("signature", generate_signature(room_id, user_id)))
        wss_url = f"wss://webcast100-ws-web-hl.douyin.com/webcast/im/push/v2/?{urlencode(params.get())}"
        self.ws = WebSocketApp(
            url=wss_url,
            header={"Pragma": "no-cache", "Accept-Language": "zh-CN,zh;q=0.9",
                    "User-Agent": HeaderBuilder.ua, "Upgrade": "websocket",
                    "Cache-Control": "no-cache", "Connection": "Upgrade"},
            cookie=self.auth_.cookie_str,
            on_message=self.on_message, on_error=self.on_error,
            on_close=self.on_close, on_open=self.on_open,
        )
        self.ws.run_forever(origin="https://live.douyin.com")

    def start(self):
        self._stopping = False
        self._thread = threading.Thread(target=self._start_ws, daemon=True)
        self._thread.start()

    def stop(self):
        self._stopping = True
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _publish(self, evt_type: str, data: dict):
        event_bus.publish(f"live:{self.live_id}", {"type": evt_type, "data": data})
