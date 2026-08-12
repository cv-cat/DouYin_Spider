"""私信服务:接收桥管理 + 创建会话 + 发送。"""
import asyncio

from webapp.backend.bridges.msg_bridge import MsgBridge


class MessageService:
    def __init__(self):
        self._bridge: MsgBridge | None = None

    def start_recv(self, auth) -> dict:
        if self._bridge is not None:
            return {"running": True, "msg": "已在接收"}
        self._bridge = MsgBridge(auth)
        self._bridge.start()
        return {"running": True, "msg": "已开始接收"}

    def stop_recv(self) -> dict:
        if self._bridge:
            self._bridge.stop()
            self._bridge = None
            return {"running": False, "msg": "已停止"}
        return {"running": False, "msg": "未在接收"}

    def status(self) -> bool:
        return self._bridge is not None

    async def resolve_uid(self, auth, user_url: str = "", to_user_id: int | None = None) -> int:
        from dy_apis.douyin_api import DouyinAPI
        if to_user_id:
            return to_user_id
        if not user_url:
            raise ValueError("需要 user_url 或 to_user_id")
        info = await asyncio.to_thread(DouyinAPI.get_user_info, auth, user_url)
        return info["user"]["uid"]

    async def create_conversation(self, auth, to_user_id: int):
        from dy_apis.douyin_api import DouyinAPI
        return await asyncio.to_thread(DouyinAPI.create_conversation, auth, to_user_id)

    async def send_msg(self, auth, conversation_id, conversation_short_id, ticket, content: str):
        from dy_apis.douyin_api import DouyinAPI
        return await asyncio.to_thread(DouyinAPI.send_msg, auth, conversation_id,
                                       conversation_short_id, ticket, content)

    async def send_to_user(self, auth, content: str, to_user_id: int | None = None,
                           user_url: str | None = None):
        """一站式:解析 uid → 建会话 → 发送。返回会话信息便于复用。"""
        uid = await self.resolve_uid(auth, user_url or "", to_user_id)
        cid, short_id, ticket = await self.create_conversation(auth, uid)
        ok = await self.send_msg(auth, cid, short_id, ticket, content)
        return {"success": ok, "conversation_id": cid,
                "conversation_short_id": short_id, "ticket": ticket}
