"""搜索服务。"""
import asyncio
import os

from webapp.backend import config


def _base_path():
    return {"media": config.MEDIA_DIR, "excel": config.EXCEL_DIR}


async def users(auth, query: str, num: int = 20):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.search_some_user, auth, query, num)


async def lives(auth, query: str, num: int = 20):
    from dy_apis.douyin_api import DouyinAPI
    return await asyncio.to_thread(DouyinAPI.search_some_live, auth, query, num)


def works(auth, query: str, num: int = 20, sort_type: str = "0", publish_time: str = "0",
          filter_duration: str = "", search_range: str = "0", content_type: str = "0",
          save_choice: str = "", excel_name: str = ""):
    """搜索作品任务 worker。"""
    from dy_apis.douyin_api import DouyinAPI
    from utils.data_util import handle_work_info, download_work, save_to_xlsx

    def worker(progress_cb, *_):
        progress_cb(0.1, None)
        raw_list = DouyinAPI.search_some_general_work(
            auth, query, num, sort_type, publish_time,
            filter_duration, search_range, content_type)
        out = []
        total = max(len(raw_list), 1)
        for i, w in enumerate(raw_list):
            info = handle_work_info(w["aweme_info"])
            out.append(info)
            if save_choice and (save_choice == "all" or "media" in save_choice):
                try:
                    download_work(info, _base_path()["media"], save_choice)
                except Exception:
                    pass
            progress_cb(0.1 + 0.8 * (i + 1) / total, None)
        if save_choice in ("all", "excel"):
            name = excel_name or query
            fp = os.path.abspath(os.path.join(_base_path()["excel"], f"{name}.xlsx"))
            save_to_xlsx(out, fp)
        progress_cb(1.0, out)
        return out
    return worker
