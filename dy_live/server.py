import os
import sys
import argparse
import gzip
import threading
import time
from urllib.parse import urlencode

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from websocket import WebSocketApp

import static.Live_pb2 as Live_pb2
from dy_live.guest_live import DouyinGuestLive
from dy_live.room_resolver import LiveRoomResolver


class DouyinLive:
    def __init__(self, live_id, auth_):
        self.auth_ = auth_
        self.live_id = live_id
        self.ws = None

    def ping(self, ws):
        while True:
            frame = Live_pb2.PushFrame()
            frame.payloadType = "hb"
            try:
                ws.send(frame.SerializeToString(), opcode=0x02)
                time.sleep(5)
            except Exception as e:
                ws.close()
                break

    def on_open(self, ws):
        print("\033[32m### opened ###\033[m")
        threading.Thread(target=self.ping, args=(ws,)).start()

    def on_message(self, ws, message):
        try:
            frame = Live_pb2.PushFrame()
            frame.ParseFromString(message)
            origin_bytes = gzip.decompress(frame.payload)
            response = Live_pb2.LiveResponse()
            response.ParseFromString(origin_bytes)
            if response.needAck:
                s = Live_pb2.PushFrame()
                s.payloadType = "ack"
                # s.payload = frame.headersList[1].value.encode('utf-8')
                s.payload = response.internalExt.encode('utf-8')
                s.logId = frame.logId
                ws.send(s.SerializeToString(), opcode=0x02)
            for item in response.messagesList:
                if item.method == 'WebcastGiftMessage':
                    message = Live_pb2.GiftMessage()
                    message.ParseFromString(item.payload)
                    # print(f'\033[1;37;40m[礼物]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 送出 \033[4;30;44m{message.gift.name}\033[m x {message.comboCount}')
                    # 谁给谁送了什么礼物
                    print(f'\033[1;37;40m[礼物]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 送给 \033[1;37;40m{message.toUser.sec_uid} - {message.toUser.nickname}\033[m \033[4;30;44m{message.gift.name}\033[m x {message.comboCount}')
                elif item.method == "WebcastChatMessage":
                    message = Live_pb2.ChatMessage()
                    message.ParseFromString(item.payload)
                    # 用户等级
                    # print(message.user.badge_image_list[0])
                    print(f'\033[1;37;40m[消息]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m : \033[4;30;44m{message.content}\033[m')
                elif item.method == "WebcastMemberMessage":
                    message = Live_pb2.MemberMessage()
                    message.ParseFromString(item.payload)
                    print(f'\033[1;37;40m[进入]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 进入直播间')
                elif item.method == "WebcastLikeMessage":
                    message = Live_pb2.LikeMessage()
                    message.ParseFromString(item.payload)
                    print(f'\033[1;37;40m[点赞]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 点赞了 {message.count} 次')
                    print(f'\033[1;37;40m[点赞]点赞总数 = {message.total}\033[m')
                elif item.method == "WebcastSocialMessage":
                    message = Live_pb2.SocialMessage()
                    message.ParseFromString(item.payload)
                    if message.action == 1:
                        print(f'\033[1;37;40m[关注]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 关注主播')
                elif item.method == "WebcastRoomStatsMessage":
                    message = Live_pb2.RoomStatsMessage()
                    message.ParseFromString(item.payload)
                    print(f'\033[1;37;40m[房间信息] {message.displayLong}')

            # s = zlib.decompress(decode_str).decode()
        except Exception as e:
            print('error')
            print(str(e))

    def on_error(self, ws, error):
        print("\033[31m### error ###")
        print(error)
        print("### ===error=== ###\033[m")

    def on_close(self, ws, close_status_code, close_msg):
        # 此处判断是否需要重连 判断直播间是否关闭
        self.start_ws()
        print("\033[31m### closed ###")
        print(f"status_code: {close_status_code}, msg: {close_msg}")
        print("### ===closed=== ###\033[m")

    def start_ws(self):
        from dy_apis.douyin_api import DouyinAPI
        from builder.header import HeaderBuilder
        from builder.params import Params
        from utils.dy_util import generate_signature

        room_info = DouyinAPI.get_live_info(self.auth_, self.live_id)
        room_id = room_info['room_id']
        user_id = room_info['user_id']
        ttwid = room_info['ttwid']
        params = Params()

        res = DouyinAPI.get_webcast_detail(self.auth_, str(user_id), room_id, f"https://live.douyin.com/{self.live_id}")
        frame = Live_pb2.LiveResponse()
        frame.ParseFromString(res)
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
            self.ws.run_forever(origin='https://live.douyin.com')
        except Exception as e:
            print(str(e))
            self.ws.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="抖音直播监听入口")
    parser.add_argument("--mode", choices=["auth", "guest"], default="guest", help="监听模式")
    parser.add_argument("--room", default="118465410901", help="直播间链接、短链或房间号")
    parser.add_argument("--sessionid", default="", help="游客态可选 sessionid")
    parser.add_argument(
        "--quiet-unknown",
        action="store_true",
        help="游客态不打印未处理消息类型",
    )
    args = parser.parse_args()

    resolver = LiveRoomResolver()
    room_info = resolver.resolve(args.room)

    if args.mode == "guest":
        live = DouyinGuestLive(
            room_input=args.room,
            room_info=room_info,
            session_id=args.sessionid,
            print_unknown=not args.quiet_unknown,
        )
        live.start()
    else:
        import utils.common_util as common_util

        common_util.load_env()
        if not common_util.dy_live_auth:
            raise RuntimeError("登录态模式缺少 DY_LIVE_COOKIES")
        live = DouyinLive(room_info.web_rid, common_util.dy_live_auth)
        live.start_ws()
