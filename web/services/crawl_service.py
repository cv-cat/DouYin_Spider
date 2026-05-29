import json

from dy_apis.douyin_api import DouyinAPI
from main import Data_Spider


class CrawlService:
    def __init__(self, config, session_service, task_manager):
        self.config = config
        self.sessions = session_service
        self.task_manager = task_manager
        self.data_spider = Data_Spider()
        self.api = DouyinAPI()

    def _auth(self):
        auth = self.sessions.load_auth("douyin")
        if auth is None:
            raise RuntimeError("Missing douyin cookie")
        return auth

    def lookup_work(self, work_url):
        return self.data_spider.spider_work(self._auth(), work_url)

    def lookup_user(self, user_url):
        return self.api.get_user_info(self._auth(), user_url)

    def search_general(self, query, require_num, sort_type, publish_time, filter_duration="", search_range="", content_type=""):
        return self.api.search_some_general_work(
            self._auth(),
            query,
            int(require_num),
            sort_type,
            publish_time,
            filter_duration,
            search_range,
            content_type,
        )

    def queue_user_export(self, user_url, save_choice="all"):
        base_path = {
            "media": str(self.config.media_dir),
            "excel": str(self.config.excel_dir),
        }
        return self.task_manager.submit(
            "crawl.user_all",
            user_url,
            lambda: self.data_spider.spider_user_all_work(self._auth(), user_url, base_path, save_choice),
        )

    def digg(self, aweme_id, digg_type="1"):
        return self.api.digg(self._auth(), aweme_id, digg_type)

    def publish_comment(self, aweme_id, content, reply_id=""):
        return self.api.publish_comment(self._auth(), aweme_id, content, reply_id)

    def collect_aweme(self, aweme_id, action="1"):
        return self.api.collect_aweme(self._auth(), aweme_id, action)

    def queue_works_export(self, works_text, save_choice="all", excel_name=""):
        works = [line.strip() for line in works_text.splitlines() if line.strip()]
        export_name = excel_name or "works-export"
        base_path = {
            "media": str(self.config.media_dir),
            "excel": str(self.config.excel_dir),
        }
        return self.task_manager.submit(
            "crawl.some_work",
            export_name,
            lambda: self.data_spider.spider_some_work(
                self._auth(),
                works,
                base_path,
                save_choice,
                export_name,
            ),
        )

    def queue_search_export(
        self,
        query,
        require_num,
        save_choice,
        sort_type,
        publish_time,
        filter_duration="",
        search_range="",
        content_type="",
        excel_name="",
    ):
        export_name = excel_name or query
        base_path = {
            "media": str(self.config.media_dir),
            "excel": str(self.config.excel_dir),
        }
        return self.task_manager.submit(
            "crawl.search_export",
            export_name,
            lambda: self.data_spider.spider_some_search_work(
                self._auth(),
                query,
                int(require_num),
                base_path,
                save_choice,
                sort_type,
                publish_time,
                filter_duration,
                search_range,
                content_type,
                export_name,
            ),
        )

    def invoke(self, operation, payload):
        auth = self._auth()
        comment = json.loads(payload["comment_json"]) if payload.get("comment_json") else None
        dispatch = {
            "get_user_work_info": lambda: self.api.get_user_work_info(auth, payload["user_url"], payload.get("max_cursor", "0")),
            "get_work_out_comment": lambda: self.api.get_work_out_comment(auth, payload["work_url"], payload.get("cursor", "0")),
            "get_work_all_out_comment": lambda: self.api.get_work_all_out_comment(auth, payload["work_url"]),
            "get_work_inner_comment": lambda: self.api.get_work_inner_comment(
                auth,
                comment,
                payload.get("cursor", "0"),
                payload.get("count", "3"),
            ),
            "get_work_all_inner_comment": lambda: self.api.get_work_all_inner_comment(auth, comment),
            "get_work_all_comment": lambda: self.api.get_work_all_comment(auth, payload["work_url"]),
            "search_general_work": lambda: self.api.search_general_work(
                auth,
                payload["query"],
                payload.get("sort_type", "0"),
                payload.get("publish_time", "0"),
                payload.get("offset", "0"),
                payload.get("search_range", ""),
                payload.get("filter_duration", ""),
                payload.get("content_type", ""),
            ),
            "search_some_user": lambda: self.api.search_some_user(auth, payload["query"], int(payload.get("num", "25"))),
            "search_user": lambda: self.api.search_user(
                auth,
                payload["query"],
                payload.get("offset", "0"),
                payload.get("num", "25"),
                payload.get("douyin_user_fans", ""),
                payload.get("douyin_user_type", ""),
            ),
            "search_live": lambda: self.api.search_live(auth, payload["query"], payload.get("offset", "0"), payload.get("num", "25")),
            "search_some_live": lambda: self.api.search_some_live(auth, payload["query"], int(payload.get("num", "25"))),
            "get_user_favorite": lambda: self.api.get_user_favorite(
                auth,
                payload["sec_id"],
                payload.get("max_cursor", "0"),
                payload.get("num", "18"),
            ),
            "get_my_uid": lambda: self.api.get_my_uid(auth),
            "get_my_sec_uid": lambda: self.api.get_my_sec_uid(auth),
            "move_collect_aweme": lambda: self.api.move_collect_aweme(
                auth,
                payload["aweme_id"],
                payload["collect_name"],
                payload["collect_id"],
            ),
            "remove_collect_aweme": lambda: self.api.remove_collect_aweme(
                auth,
                payload["aweme_id"],
                payload["collect_name"],
                payload["collect_id"],
            ),
            "get_collect_list": lambda: self.api.get_collect_list(auth),
            "get_user_follower_list": lambda: self.api.get_user_follower_list(
                auth,
                payload["user_id"],
                payload["sec_id"],
                payload.get("max_time", "0"),
                payload.get("count", "20"),
            ),
            "get_some_user_follower_list": lambda: self.api.get_some_user_follower_list(
                auth,
                payload["user_id"],
                payload["sec_id"],
                int(payload.get("num", "20")),
            ),
            "get_user_following_list": lambda: self.api.get_user_following_list(
                auth,
                payload["user_id"],
                payload["sec_id"],
                payload.get("max_time", "0"),
                payload.get("count", "20"),
            ),
            "get_some_user_following_list": lambda: self.api.get_some_user_following_list(
                auth,
                payload["user_id"],
                payload["sec_id"],
                int(payload.get("num", "20")),
            ),
            "get_notice_list": lambda: self.api.get_notice_list(
                auth,
                payload.get("min_time", "0"),
                payload.get("max_time", "0"),
                payload.get("count", "10"),
                payload.get("notice_group", "700"),
            ),
            "get_some_notice_list": lambda: self.api.get_some_notice_list(
                auth,
                int(payload.get("num", "20")),
                payload.get("notice_group", "700"),
            ),
            "get_feed": lambda: self.api.get_feed(
                auth,
                payload.get("count", "20"),
                payload.get("refresh_index", "2"),
            ),
            "get_device_id": lambda: self.api.get_device_id(auth),
            "search_some_video_work": lambda: self.api.search_some_video_work(
                auth,
                payload["query"],
                int(payload.get("num", "16")),
                payload.get("sort_type", "0"),
                payload.get("publish_time", "0"),
                payload.get("filter_duration", ""),
            ),
            "search_video_work": lambda: self.api.search_video_work(
                auth,
                payload["query"],
                payload.get("offset", "0"),
                payload.get("count", "16"),
                payload.get("sort_type", "0"),
                payload.get("publish_time", "0"),
                payload.get("filter_duration", ""),
            ),
        }
        if operation not in dispatch:
            raise ValueError(f"Unsupported crawl operation: {operation}")
        return dispatch[operation]()
