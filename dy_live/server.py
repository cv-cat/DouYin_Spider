import base64
import gzip
import json
import sys
import threading
from collections import OrderedDict
from urllib.parse import urlencode

from websocket import WebSocketApp

import static.Live_pb2 as Live_pb2
from dy_live.pk import PK_MESSAGES, PKMessageHandler, print_pk_event
from dy_apis.douyin_api import DouyinAPI
from builder.header import HeaderBuilder
from builder.params import Params
import utils.common_util as common_util
from utils.dy_util import generate_signature

# Windows 控制台是 GBK，弹幕含 emoji 会 UnicodeEncodeError，按 UTF-8 输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class DouyinLive:
    def __init__(self, live_id, auth_, on_pk_event=None, on_chat_event=None,
                 on_gift_event=None):
        self.auth_ = auth_
        self.live_id = live_id
        self.ws = None
        # Optional structured PK consumer; normal CLI printing stays enabled.
        self.on_pk_event = on_pk_event
        self.on_chat_event = on_chat_event
        self.on_gift_event = on_gift_event
        self.pk_handler = PKMessageHandler()
        self._seen_messages = OrderedDict()
        self._stop_event = threading.Event()
        self._heartbeat_stop = threading.Event()
        self._run_lock = threading.Lock()

    def ping(self, ws, stop_event=None):
        stop_event = stop_event or self._heartbeat_stop
        while not stop_event.is_set() and not self._stop_event.is_set():
            frame = Live_pb2.PushFrame()
            frame.payloadType = "hb"
            try:
                ws.send(frame.SerializeToString(), opcode=0x02)
            except Exception:
                ws.close()
                break
            if stop_event.wait(5):
                break

    def on_open(self, ws):
        print("\033[32m### opened ###\033[m")
        if self._stop_event.is_set():
            ws.close()
            return
        if hasattr(self.auth_, "live_websocket_connected"):
            self.auth_.live_websocket_connected = True
        self._heartbeat_stop.set()
        self._heartbeat_stop = threading.Event()
        threading.Thread(target=self.ping, args=(ws, self._heartbeat_stop),
                         name='douyin-live-heartbeat', daemon=True).start()

    def _dispatch_response(self, response):
        """Dispatch HTTP bootstrap and WS batches identically, isolating items."""
        for item in response.messagesList:
            method = item.method.removeprefix('Webcast')
            key = (method, item.msgId)
            if item.msgId and key in self._seen_messages:
                continue
            if item.msgId:
                self._seen_messages[key] = None
                if len(self._seen_messages) > 4096:
                    self._seen_messages.popitem(last=False)
            try:
                self._dispatch_message(item, method)
            except Exception as exc:
                label = 'PK 消息处理失败' if method in PK_MESSAGES else '直播消息处理失败'
                print(f'[{label}] method={item.method} msg_id={item.msgId}: {exc}')

    def _dispatch_message(self, item, method):
        if method in PK_MESSAGES:
            event = self.pk_handler.handle(item.method, item.payload, item.msgId)
            if event is not None:
                print_pk_event(event)
                if self.on_pk_event is not None:
                    self.on_pk_event(event)
        elif method == 'GiftMessage':
            message = Live_pb2.GiftMessage.FromString(item.payload)
            event = self._gift_event(message, item)
            print(f'\033[1;37;40m[礼物]SEC_UID = {event["sec_uid"]} - {event["nickname"]}\033[m 送给 \033[1;37;40m{event["to_sec_uid"]} - {event["to_nickname"]}\033[m \033[4;30;44m{event["gift_name"]}\033[m x {event["quantity"]} ({event["diamond_total"]}抖币)')
            if self.on_gift_event is not None:
                self.on_gift_event(event)
        elif method == 'ChatMessage':
            message = Live_pb2.ChatMessage.FromString(item.payload)
            event = dict(type='chat', method=item.method,
                         msg_id=str(item.msgId) if item.msgId else None,
                         uid=message.user.id_str or (str(message.user.id) if message.user.id else None),
                         sec_uid=message.user.sec_uid, nickname=message.user.nickname,
                         content=message.content)
            print(f'\033[1;37;40m[消息]UID = {event["uid"]} SEC_UID = {event["sec_uid"]} - {event["nickname"]}\033[m : \033[4;30;44m{event["content"]}\033[m')
            if self.on_chat_event is not None:
                self.on_chat_event(event)
        elif method == 'MemberMessage':
            message = Live_pb2.MemberMessage.FromString(item.payload)
            print(f'\033[1;37;40m[进入]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 进入直播间')
        elif method == 'LikeMessage':
            message = Live_pb2.LikeMessage.FromString(item.payload)
            print(f'\033[1;37;40m[点赞]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 点赞了 {message.count} 次')
            print(f'\033[1;37;40m[点赞]点赞总数 = {message.total}\033[m')
        elif method == 'SocialMessage':
            message = Live_pb2.SocialMessage.FromString(item.payload)
            if message.action == 1:
                print(f'\033[1;37;40m[关注]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 关注主播')
        elif method == 'RoomStatsMessage':
            message = Live_pb2.RoomStatsMessage.FromString(item.payload)
            print(f'\033[1;37;40m[房间信息] {message.displayLong}')

    @staticmethod
    def _gift_event(message, item):
        """Normalize GiftMessage without losing compound-gift metadata.

        ``gift.diamondCount`` is the catalog/base unit price.  Compound or
        upgraded gifts can carry their extra display information in
        ``diyItemInfo``/``interactGiftInfo`` (and in the opaque effect blobs).
        An explicit variant price is used when present; otherwise those
        fields are returned verbatim instead of guessing a price.
        """
        gift = message.gift
        quantity = (message.totalCount or message.comboCount or
                    message.repeatCount or message.groupCount or 1)
        unit_price = int(gift.diamondCount)
        variant_price = DouyinLive._variant_diamond_count(
            message.interactGiftInfo, message.diyItemInfo)
        effective_price = variant_price or unit_price
        event = dict(
            type='gift',
            method=item.method,
            msg_id=str(item.msgId) if item.msgId else None,
            uid=message.user.id_str or (str(message.user.id) if message.user.id else None),
            sec_uid=message.user.sec_uid,
            nickname=message.user.nickname,
            to_uid=message.toUser.id_str or (str(message.toUser.id) if message.toUser.id else None),
            to_sec_uid=message.toUser.sec_uid,
            to_nickname=message.toUser.nickname,
            gift_id=str(message.giftId or gift.id),
            gift_name=gift.name,
            diamond_count=unit_price,
            quantity=int(quantity),
            diamond_total=effective_price * int(quantity),
            variant_diamond_count=variant_price,
            diamond_price_source=('variant_metadata' if variant_price
                                  else 'gift.diamondCount'),
            fan_ticket_count=int(message.fanTicketCount),
            combo_count=int(message.comboCount),
            repeat_count=int(message.repeatCount),
            group_count=int(message.groupCount),
            total_count=int(message.totalCount),
            group_id=str(message.groupId) if message.groupId else None,
            interact_gift_info=message.interactGiftInfo,
            diy_item_info=message.diyItemInfo,
        )
        # Keep opaque effect/tray data available for callers that need to
        # resolve a compound gift, while keeping the callback JSON-friendly.
        if message.trayInfo:
            event['tray_info_b64'] = base64.b64encode(message.trayInfo).decode()
        if message.assetEffectMixInfo:
            event['asset_effect_mix_info_b64'] = base64.b64encode(
                message.assetEffectMixInfo).decode()
        if message.assetEffectMixInfoLegacy:
            event['asset_effect_mix_info_legacy_b64'] = base64.b64encode(
                message.assetEffectMixInfoLegacy).decode()
        return event

    @staticmethod
    def _variant_diamond_count(*raw_values):
        """Read an explicit compound-gift price when Douyin sends one.

        Most ``diyItemInfo`` payloads only identify an animation asset and do
        not contain money information.  In that case returning ``None`` is
        intentional: the base ``gift.diamondCount`` must not be silently
        changed to a guessed value.
        """
        keys = ('diamond_count', 'diamondCount', 'gift_diamond_count',
                'giftDiamondCount', 'gift_price', 'giftPrice')
        for raw in raw_values:
            if not raw:
                continue
            try:
                value = json.loads(raw) if isinstance(raw, str) else raw
            except (TypeError, ValueError):
                continue
            stack = [value]
            while stack:
                current = stack.pop()
                if isinstance(current, dict):
                    for key in keys:
                        candidate = current.get(key)
                        if isinstance(candidate, (int, float, str)):
                            try:
                                candidate = int(candidate)
                            except (TypeError, ValueError):
                                continue
                            if candidate > 0:
                                return candidate
                    stack.extend(current.values())
                elif isinstance(current, list):
                    stack.extend(current)
        return None

    def on_message(self, ws, message):
        try:
            frame = Live_pb2.PushFrame()
            frame.ParseFromString(message)
            if frame.payloadType in ('hb', 'ack') or not frame.payload:
                return
            origin_bytes = frame.payload
            if origin_bytes.startswith(b'\x1f\x8b'):
                origin_bytes = gzip.decompress(origin_bytes)
            response = Live_pb2.LiveResponse()
            response.ParseFromString(origin_bytes)
            if hasattr(self.auth_, "live_websocket_verified"):
                # A successful protobuf parse proves the websocket payload
                # path, whereas on_open alone only proves the handshake.
                self.auth_.live_websocket_verified = True
            if response.needAck:
                s = Live_pb2.PushFrame()
                s.payloadType = "ack"
                s.payload = response.internalExt.encode('utf-8')
                s.logId = frame.logId
                try:
                    ws.send(s.SerializeToString(), opcode=0x02)
                except Exception as exc:
                    # Messages already received are still useful if sending an
                    # ACK fails during disconnect; do not drop this batch.
                    print(f'[直播 ACK 失败] {exc}')
            self._dispatch_response(response)
        except Exception as e:
            print('error')
            print(str(e))

    def on_error(self, ws, error):
        print("\033[31m### error ###")
        print(error)
        print("### ===error=== ###\033[m")

    def on_close(self, ws, close_status_code, close_msg):
        self._heartbeat_stop.set()
        print("\033[31m### closed ###")
        print(f"status_code: {close_status_code}, msg: {close_msg}")
        print("### ===closed=== ###\033[m")

    def stop(self):
        """Stop the receive loop and prevent on_close from recursively reconnecting."""
        self._stop_event.set()
        self._heartbeat_stop.set()
        ws, self.ws = self.ws, None
        if ws is not None:
            ws.close()

    def start_ws(self):
        room_info = DouyinAPI.get_live_info(self.auth_, self.live_id)
        room_id = room_info['room_id']
        user_id = room_info['user_id']
        ttwid = room_info['ttwid']
        params = Params()

        res = DouyinAPI.get_webcast_detail(self.auth_, str(user_id), room_id, f"https://live.douyin.com/{self.live_id}")
        frame = Live_pb2.LiveResponse()
        frame.ParseFromString(res)
        # The initial fetch is itself a LiveResponse. Dispatch it before the
        # websocket so early chat/gift/PK messages are not silently discarded.
        if hasattr(self.auth_, "live_websocket_verified"):
            self.auth_.live_websocket_verified = True
        self._dispatch_response(frame)
        (params
         .add_param('app_name', 'douyin_web')
         .add_param('version_code', '180800')
         .add_param('webcast_sdk_version', '1.0.15')
         .add_param('update_version_code', '1.0.15')
         .add_param('compress', 'gzip')
         .add_param('device_platform', 'web')
         .add_param('cookie_enabled', 'true')
         .add_param('screen_width', '1707')
         .add_param('screen_height', '960')
         .add_param('browser_language', 'zh-CN')
         .add_param('browser_platform', 'Win32')
         .add_param('browser_name', 'Mozilla')
         .add_param('browser_version',
                    HeaderBuilder.ua.split('Mozilla/')[-1])
         .add_param('browser_online', 'true')
         .add_param('tz_name', 'Etc/GMT-8')
         .add_param('cursor', str(frame.cursor))
         .add_param('internal_ext', frame.internalExt)
         .add_param('host', 'https://live.douyin.com')
         .add_param('aid', '6383')
         .add_param('live_id', '1')
         .add_param('did_rule', '3')
         .add_param('endpoint', 'live_pc')
         .add_param('support_wrds', '1')
         .add_param('user_unique_id', str(user_id))
         .add_param('im_path', '/webcast/im/fetch/')
         .add_param('identity', 'audience')
         .add_param('need_persist_msg_count', '15')
         .add_param('insert_task_id', '')
         .add_param('live_reason', '')
         .add_param('room_id', room_id)
         .add_param('heartbeatDuration', '0')
         .add_param('signature', generate_signature(room_id, user_id))
         )
        wss_url = f"wss://webcast100-ws-web-hl.douyin.com/webcast/im/push/v2/?{urlencode(params.get())}"
        self.ws = WebSocketApp(
            url=wss_url,
            header={
                'Pragma': 'no-cache',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                'User-Agent': HeaderBuilder.ua,
                'Upgrade': 'websocket',
                'Cache-Control': 'no-cache',
                'Connection': 'Upgrade',
            },
            cookie=self.auth_.cookie_str,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        try:
            self._stop_event.clear()
            self.ws.run_forever(origin='https://live.douyin.com', reconnect=3)
        except Exception as e:
            print(str(e))
            self.ws.close()


if __name__ == '__main__':
    common_util.load_env()
    live_id = "432433667143"
    # Live REST/WebSocket uses the same Auth session as the main-site APIs;
    # an explicit DY_LIVE_COOKIES remains an opt-in legacy override handled by
    # load_env().
    live = DouyinLive(live_id, common_util.get_live_auth())
    live.start_ws()
