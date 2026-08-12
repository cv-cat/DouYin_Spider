"""直播服务:监听桥管理 + 点赞/发弹幕。"""
import asyncio

from webapp.backend.bridges.live_bridge import LiveBridge


class LiveService:
    def __init__(self):
        self._bridges: dict[str, LiveBridge] = {}

    def start(self, room_id: str, auth) -> dict:
        if room_id in self._bridges:
            return {"room_id": room_id, "running": True, "msg": "已在监听"}
        bridge = LiveBridge(room_id, auth)
        self._bridges[room_id] = bridge
        bridge.start()
        return {"room_id": room_id, "running": True, "msg": "已开始监听"}

    def stop(self, room_id: str) -> dict:
        bridge = self._bridges.pop(room_id, None)
        if bridge:
            bridge.stop()
            return {"room_id": room_id, "running": False, "msg": "已停止"}
        return {"room_id": room_id, "running": False, "msg": "未在监听"}

    def status(self) -> list[str]:
        return list(self._bridges.keys())

    async def digg(self, auth, room_id: str, count: str = "1"):
        from dy_apis.douyin_api import DouyinAPI
        return await asyncio.to_thread(DouyinAPI.diggLiveRoom, auth, room_id, count)

    async def send(self, auth, room_id: str, content: str):
        from dy_apis.douyin_api import DouyinAPI
        return await asyncio.to_thread(DouyinAPI.sendMsgInRoom, auth, room_id, content)
