import gzip
import hashlib
import os
import random
import threading
import time
from typing import Callable, Dict, Optional
from urllib.parse import urlencode, urlparse, parse_qsl

import requests
from py_mini_racer import MiniRacer
from websocket import WebSocketApp

import static.Live_pb2 as Live_pb2
from dy_live.room_resolver import DEFAULT_USER_AGENT, LiveRoomInfo, LiveRoomResolver


EventCallback = Callable[[Dict], None]
RawCallback = Callable[[str, bytes], None]
StatusCallback = Callable[[str, bool], None]


def _resource_path(relative_path: str) -> str:
    return os.path.join(os.path.dirname(__file__), relative_path)


def generate_guest_signature(wss_url: str, script_file: str = "sign.js") -> Optional[str]:
    """游客态 websocket 签名。"""

    keys = (
        "live_id,aid,version_code,webcast_sdk_version,room_id,sub_room_id,"
        "sub_channel_id,did_rule,user_unique_id,device_platform,device_type,ac,identity"
    ).split(",")
    query_pairs = dict(parse_qsl(urlparse(wss_url).query, keep_blank_values=True))
    sign_source = ",".join(f"{key}={query_pairs.get(key, '')}" for key in keys)
    x_ms_stub = hashlib.md5(sign_source.encode("utf-8")).hexdigest()

    with open(_resource_path(script_file), "r", encoding="utf-8") as file:
        script = file.read()

    ctx = MiniRacer()
    ctx.eval(script)
    return ctx.call("get_sign", x_ms_stub)


class DouyinGuestLive:
    """游客态直播间监听器。"""

    WS_BASE_URL = "wss://webcast100-ws-web-lf.douyin.com/webcast/im/push/v2/"

    def __init__(
        self,
        room_input: str,
        room_info: Optional[LiveRoomInfo] = None,
        *,
        session_id: str = "",
        cookie_str: str = "",
        user_agent: str = DEFAULT_USER_AGENT,
        on_event: Optional[EventCallback] = None,
        on_raw_message: Optional[RawCallback] = None,
        on_status: Optional[StatusCallback] = None,
        auto_reconnect: bool = True,
        print_unknown: bool = True,
        verbose: bool = True,
    ):
        self.room_input = room_input
        self.room_info = room_info
        self.session_id = session_id
        self.cookie_str = cookie_str
        self.user_agent = user_agent
        self.on_event = on_event
        self.on_raw_message = on_raw_message
        self.on_status = on_status
        self.auto_reconnect = auto_reconnect
        self.print_unknown = print_unknown
        self.verbose = verbose

        self.ws = None
        self.stop_event = threading.Event()
        self.heartbeat_thread = None
        self.last_message_at = 0.0
        self.resolver = LiveRoomResolver(user_agent=user_agent)
        self._visitor_id = self._random_digits(19)
        self._handlers = {
            "WebcastChatMessage": self._parse_chat_message,
            "WebcastGiftMessage": self._parse_gift_message,
            "WebcastMemberMessage": self._parse_member_message,
            "WebcastLikeMessage": self._parse_like_message,
            "WebcastSocialMessage": self._parse_social_message,
            "WebcastRoomStatsMessage": self._parse_room_stats_message,
        }

    @staticmethod
    def _random_digits(length: int = 19) -> str:
        return "".join(random.choice("0123456789") for _ in range(length))

    def start(self):
        self.stop_event.clear()
        if not self.room_info:
            self.room_info = self.resolver.resolve(self.room_input, cookie_str=self.cookie_str)
        self._connect()

    def stop(self):
        self.stop_event.set()
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _build_cookie(self) -> str:
        ttwid = self.room_info.ttwid or self._get_ttwid()
        cookies = [f"ttwid={ttwid}"]
        if self.session_id:
            cookies.append(f"sessionid={self.session_id}")
        if self.cookie_str:
            cookies.append(self.cookie_str)
        return ";".join(item for item in cookies if item)

    def _get_ttwid(self) -> str:
        response = requests.get(
            "https://live.douyin.com/",
            headers={"User-Agent": self.user_agent},
            timeout=10,
        )
        ttwid = response.cookies.get("ttwid", "")
        if ttwid:
            self.room_info.ttwid = ttwid
        return ttwid

    def _build_wss_url(self) -> str:
        now_ms = int(time.time() * 1000)
        first_req_ms = now_ms - random.randint(50, 300)
        fetch_time = now_ms
        user_unique_id = self.room_info.user_unique_id or self._visitor_id
        cursor_random = self._random_digits(19)
        wrds_v = self._random_digits(19)
        internal_ext = (
            f"internal_src:dim|wss_push_room_id:{self.room_info.room_id}|"
            f"wss_push_did:{user_unique_id}|first_req_ms:{first_req_ms}|"
            f"fetch_time:{fetch_time}|seq:1|wss_info:0-{fetch_time}-0-0|"
            f"wrds_v:{wrds_v}"
        )

        params = [
            ("app_name", "douyin_web"),
            ("version_code", "180800"),
            ("webcast_sdk_version", "1.0.14-beta.0"),
            ("update_version_code", "1.0.14-beta.0"),
            ("compress", "gzip"),
            ("device_platform", "web"),
            ("cookie_enabled", "true"),
            ("screen_width", "1536"),
            ("screen_height", "864"),
            ("browser_language", "zh-CN"),
            ("browser_platform", "Win32"),
            ("browser_name", "Mozilla"),
            ("browser_version", self.user_agent),
            ("browser_online", "true"),
            ("tz_name", "Asia/Shanghai"),
            ("cursor", f"d-1_u-1_fh-{cursor_random}_t-{fetch_time}_r-1"),
            ("internal_ext", internal_ext),
            ("host", "https://live.douyin.com"),
            ("aid", "6383"),
            ("live_id", "1"),
            ("did_rule", "3"),
            ("endpoint", "live_pc"),
            ("support_wrds", "1"),
            ("user_unique_id", str(user_unique_id)),
            ("im_path", "/webcast/im/fetch/"),
            ("identity", "audience"),
            ("need_persist_msg_count", "15"),
            ("insert_task_id", ""),
            ("live_reason", ""),
            ("room_id", str(self.room_info.room_id)),
            ("heartbeatDuration", "0"),
        ]
        query = urlencode(params)
        url = f"{self.WS_BASE_URL}?{query}"
        signature = generate_guest_signature(url)
        if signature:
            url = f"{url}&signature={signature}"
        return url

    def _connect(self):
        wss_url = self._build_wss_url()
        headers = {
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "User-Agent": self.user_agent,
            "Cookie": self._build_cookie(),
        }
        self.ws = WebSocketApp(
            url=wss_url,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws.run_forever(origin="https://live.douyin.com")

    def _heartbeat_loop(self, ws):
        while not self.stop_event.is_set():
            time.sleep(10)
            try:
                if ws.sock and ws.sock.connected:
                    frame = Live_pb2.PushFrame()
                    frame.payloadType = "hb"
                    ws.send(frame.SerializeToString(), opcode=0x02)
            except Exception:
                break

    def _on_open(self, ws):
        self.last_message_at = time.time()
        if self.verbose:
            print(f"[游客态] 已连接直播间 {self.room_info.web_rid} / {self.room_info.room_id}")
        if self.on_status:
            self.on_status(str(self.room_info.room_id), True)
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, args=(ws,), daemon=True)
        self.heartbeat_thread.start()

    def _on_message(self, ws, message):
        self.last_message_at = time.time()
        frame = Live_pb2.PushFrame()
        frame.ParseFromString(message)

        if not frame.payload:
            return

        try:
            payload_bytes = gzip.decompress(frame.payload)
        except OSError:
            payload_bytes = frame.payload
        response = Live_pb2.LiveResponse()
        response.ParseFromString(payload_bytes)

        if response.needAck:
            ack = Live_pb2.PushFrame()
            ack.payloadType = "ack"
            ack.payload = response.internalExt.encode("utf-8")
            ack.logId = frame.logId
            ws.send(ack.SerializeToString(), opcode=0x02)

        for item in response.messagesList:
            method = item.method
            if self.on_raw_message:
                try:
                    self.on_raw_message(method, item.payload)
                except Exception:
                    pass

            parser = self._handlers.get(method)
            if not parser:
                if self.print_unknown and self.verbose:
                    print(f"[游客态-未处理] {method} payload={len(item.payload)} bytes")
                continue

            try:
                event = parser(item)
                if not event:
                    continue
                if self.on_event:
                    self.on_event(event)
                else:
                    self._print_event(event)
            except Exception as exc:
                print(f"[游客态] 处理消息失败 {method}: {exc}")

    def _on_error(self, ws, error):
        print(f"[游客态] 连接异常: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        if self.on_status:
            self.on_status(str(self.room_info.room_id), False)
        if self.verbose:
            print(f"[游客态] 连接关闭 status={close_status_code} msg={close_msg}")
        if not self.stop_event.is_set() and self.auto_reconnect:
            time.sleep(3)
            self._connect()

    def _base_event(self, method: str, item, payload_obj, action: str, extra: Optional[Dict] = None) -> Dict:
        user = getattr(payload_obj, "user", None)
        event = {
            "method": method,
            "room_id": str(self.room_info.room_id),
            "web_rid": str(self.room_info.web_rid),
            "room_title": self.room_info.room_title,
            "msg_id": getattr(item, "msgId", 0),
            "action": action,
            "nickname": getattr(user, "nickname", ""),
            "user_id": str(getattr(user, "id", "")),
            "sec_uid": getattr(user, "sec_uid", ""),
            "payload_obj": payload_obj,
        }
        if extra:
            event.update(extra)
        return event

    def _parse_chat_message(self, item) -> Dict:
        message = Live_pb2.ChatMessage()
        message.ParseFromString(item.payload)
        return self._base_event(
            "WebcastChatMessage",
            item,
            message,
            message.content,
            {"content": message.content},
        )

    def _parse_gift_message(self, item) -> Dict:
        message = Live_pb2.GiftMessage()
        message.ParseFromString(item.payload)
        target_user = getattr(message, "toUser", None)
        gift_name = getattr(message.gift, "name", "")
        combo_count = getattr(message, "comboCount", 0)
        action = f"{gift_name} x {combo_count}"
        return self._base_event(
            "WebcastGiftMessage",
            item,
            message,
            action,
            {
                "gift_name": gift_name,
                "combo_count": combo_count,
                "target_nickname": getattr(target_user, "nickname", ""),
                "target_sec_uid": getattr(target_user, "sec_uid", ""),
            },
        )

    def _parse_member_message(self, item) -> Dict:
        message = Live_pb2.MemberMessage()
        message.ParseFromString(item.payload)
        return self._base_event(
            "WebcastMemberMessage",
            item,
            message,
            "进入直播间",
            {"member_count": getattr(message, "memberCount", 0)},
        )

    def _parse_like_message(self, item) -> Dict:
        message = Live_pb2.LikeMessage()
        message.ParseFromString(item.payload)
        return self._base_event(
            "WebcastLikeMessage",
            item,
            message,
            f"点赞 {message.count} 次",
            {"count": message.count, "total": message.total},
        )

    def _parse_social_message(self, item) -> Dict:
        message = Live_pb2.SocialMessage()
        message.ParseFromString(item.payload)
        action = "关注了主播" if message.action == 1 else f"社交动作 {message.action}"
        return self._base_event(
            "WebcastSocialMessage",
            item,
            message,
            action,
            {"social_action": message.action, "follow_count": message.followCount},
        )

    def _parse_room_stats_message(self, item) -> Dict:
        message = Live_pb2.RoomStatsMessage()
        message.ParseFromString(item.payload)
        return {
            "method": "WebcastRoomStatsMessage",
            "room_id": str(self.room_info.room_id),
            "web_rid": str(self.room_info.web_rid),
            "room_title": self.room_info.room_title,
            "msg_id": getattr(item, "msgId", 0),
            "action": message.displayLong,
            "display_long": message.displayLong,
            "display_short": message.displayShort,
            "payload_obj": message,
        }

    @staticmethod
    def _print_event(event: Dict):
        method = event["method"]
        if method == "WebcastGiftMessage":
            print(
                f"[礼物] {event['nickname']} -> {event.get('target_nickname', '')} "
                f"{event.get('gift_name', '')} x {event.get('combo_count', 0)}"
            )
        elif method == "WebcastChatMessage":
            print(f"[消息] {event['nickname']}: {event.get('content', '')}")
        elif method == "WebcastMemberMessage":
            print(f"[进入] {event['nickname']} 进入直播间")
        elif method == "WebcastLikeMessage":
            print(
                f"[点赞] {event['nickname']} 点赞 {event.get('count', 0)} 次，"
                f"总点赞 {event.get('total', 0)}"
            )
        elif method == "WebcastSocialMessage":
            print(f"[关注] {event['nickname']} {event['action']}")
        elif method == "WebcastRoomStatsMessage":
            print(f"[房间信息] {event.get('display_long', '')}")
        else:
            print(f"[{method}] {event['action']}")
