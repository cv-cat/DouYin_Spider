"""采集服务:SDK 采集接口的薄封装。sync→async via to_thread。"""
import asyncio

from webapp.backend import config


def _base_path():
    return {"media": config.MEDIA_DIR, "excel": config.EXCEL_DIR}


# ---------- 同步(快) ----------
async def work_info(auth, url: str):
    from dy_apis.douyin_api import DouyinAPI
    from utils.data_util import handle_work_info

    def run():
        data = DouyinAPI.get_work_info(auth, url)
        return handle_work_info(data["aweme_detail"])
    return await asyncio.to_thread(run)


async def user_info(auth, user_url: str):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.get_user_info, auth, user_url)


async def notices(auth, num: int = 20):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.get_some_notice_list, auth, num)


async def feed(auth, count: str = "20"):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.get_feed, auth, count)


async def collect_list(auth):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.get_collect_list, auth)


async def rank(auth, room_id: str, anchor_id: str, sec_anchor_id: str):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.get_rank_list, auth, room_id, anchor_id, sec_anchor_id)


async def favorites(auth, sec_id: str, max_cursor: str = "0", num: str = "18"):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.get_user_favorite, auth, sec_id, max_cursor, num)


# ---------- 任务(慢,带进度) ----------
def user_all_work(auth, user_url: str, save_choice: str = "all", excel_name: str = ""):
    """返回任务 worker 函数:worker(progress_cb) -> result。"""
    from dy_apis.douyin_api import DouyinAPI
    from utils.data_util import handle_work_info, download_work, save_to_xlsx
    import os

    def worker(progress_cb, *_):
        progress_cb(0.05, None)
        user_info = DouyinAPI.get_user_info(auth, user_url)
        work_list = DouyinAPI.get_user_all_work_info(auth, user_url)
        total = max(len(work_list), 1)
        out = []
        if save_choice in ("all", "excel") and not excel_name:
            excel_name = user_url.split("/")[-1].split("?")[0]
        for i, w in enumerate(work_list):
            w["author"].update(user_info["user"])
            info = handle_work_info(w)
            out.append(info)
            if save_choice == "all" or "media" in save_choice:
                try:
                    download_work(info, _base_path()["media"], save_choice)
                except Exception:
                    pass
            progress_cb(0.05 + 0.9 * (i + 1) / total, None)
        if save_choice in ("all", "excel"):
            fp = os.path.abspath(os.path.join(_base_path()["excel"], f"{excel_name}.xlsx"))
            save_to_xlsx(out, fp)
        progress_cb(1.0, out)
        return out
    return worker


def all_comments(auth, url: str):
    from dy_apis.douyin_api import DouyinAPI

    def worker(progress_cb, *_):
        progress_cb(0.1, None)
        res = DouyinAPI.get_work_all_comment(auth, url)
        progress_cb(1.0, res)
        return res
    return worker


def followers(auth, user_id: str, sec_id: str, num: int = 20):
    from dy_apis.douyin_api import DouyinAPI

    def worker(progress_cb, *_):
        progress_cb(0.1, None)
        res = DouyinAPI.get_some_user_follower_list(auth, user_id, sec_id, num)
        progress_cb(1.0, res)
        return res
    return worker


def following(auth, user_id: str, sec_id: str, num: int = 20):
    from dy_apis.douyin_api import DouyinAPI

    def worker(progress_cb, *_):
        progress_cb(0.1, None)
        res = DouyinAPI.get_some_user_following_list(auth, user_id, sec_id, num)
        progress_cb(1.0, res)
        return res
    return worker
