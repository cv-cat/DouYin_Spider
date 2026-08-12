"""互动服务:点赞/评论/收藏。"""
import asyncio


async def digg(auth, aweme_id: str, digg_type: str = "1"):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.digg, auth, aweme_id, digg_type)


async def comment(auth, aweme_id: str, content: str, reply_id: str = ""):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.publish_comment, auth, aweme_id, content, reply_id)


async def collect(auth, aweme_id: str, action: str = "1"):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.collect_aweme, auth, aweme_id, action)


async def collect_move(auth, aweme_id: str, collect_name: str, collect_id: str):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.move_collect_aweme, auth, aweme_id, collect_name, collect_id)


async def collect_remove(auth, aweme_id: str, collect_name: str, collect_id: str):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.remove_collect_aweme, auth, aweme_id, collect_name, collect_id)
