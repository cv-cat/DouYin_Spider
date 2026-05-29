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
