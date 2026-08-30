import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import collect_ip_comments as collector


class FakeAPI:
    pages = {
        "0": {"status_code": 0, "comments": [{
            "cid": "c1", "aweme_id": "123", "text": "你好", "ip_label": "IP属地：湖北",
            "reply_comment_total": 1,
            "user": {"nickname": "甲", "uid": "1", "sec_uid": "sec-a"},
        }], "cursor": 10, "has_more": 1},
        "10": {"status_code": 0, "comments": [{
            "cid": "c2", "aweme_id": "123", "text": "世界", "ip_label": "IP属地：北京",
            "reply_comment_total": 0,
            "user": {"nickname": "乙", "uid": "2", "sec_uid": "sec-b"},
        }], "cursor": 20, "has_more": 0},
    }

    @staticmethod
    def get_work_out_comment(auth, url, cursor, **kwargs):
        return FakeAPI.pages[cursor]

    @staticmethod
    def get_work_all_inner_comment(auth, comment):
        return [{
            "cid": "r1", "aweme_id": "123", "text": "回复", "ip_location": "湖北",
            "user": {"nickname": "甲", "uid": "1", "sec_uid": "sec-a"},
        }]

    @staticmethod
    def get_user_info(auth, url):
        return {"status_code": 0, "user": {"gender": 1, "user_age": 25, "ip_location": "湖北"}}


class CollectorTests(unittest.TestCase):
    def test_extracts_note_aweme_id(self):
        self.assertEqual(
            "7671539215188245434",
            collector.extract_aweme_id("https://www.douyin.com/note/7671539215188245434"),
        )

    @patch.object(collector, "DouyinAPI", FakeAPI)
    def test_collect_filter_replies_and_cached_profile(self):
        rows, pages = collector.collect_comments(object(), "https://www.douyin.com/video/123", "湖北", True)
        self.assertEqual(2, pages)
        self.assertEqual(["c1", "r1"], [row["cid"] for row in rows])
        count = collector.enrich_profiles(object(), rows, interval=0)
        self.assertEqual(1, count)
        self.assertTrue(all(row["gender"] == "男" for row in rows))

    @patch.object(collector, "DouyinAPI", FakeAPI)
    def test_collect_deduplicates_comment_ids_across_pages(self):
        original = FakeAPI.pages
        FakeAPI.pages = {
            "0": {"status_code": 0, "comments": [
                {"cid": "same", "text": "one", "ip_label": "湖北", "user": {}}
            ], "cursor": 10, "has_more": 1},
            "10": {"status_code": 0, "comments": [
                {"cid": "same", "text": "one", "ip_label": "湖北", "user": {}},
                {"cid": "new", "text": "two", "ip_label": "湖北", "user": {}},
            ], "cursor": 20, "has_more": 0},
        }
        try:
            rows, _ = collector.collect_comments(object(), "url", "湖北", candidate_limit=2)
        finally:
            FakeAPI.pages = original
        self.assertEqual(["same", "new"], [row["cid"] for row in rows])

    def test_save_csv_for_excel(self):
        row = collector.comment_row({"cid": "1", "text": "中文", "ip_label": "上海"}, 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comments.csv"
            collector.save_rows([row], path)
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_recent_filter_and_time_format(self):
        china_tz = timezone(timedelta(hours=8))
        now = datetime(2026, 8, 8, 12, tzinfo=china_tz)
        three_days_ago = int((now - timedelta(days=3)).timestamp())
        self.assertEqual("三天前", collector.format_comment_time(three_days_ago, now))
        self.assertTrue(collector.is_recent({"create_time": three_days_ago}, 14, now.timestamp()))

    def test_builds_project20_handoff_command(self):
        command = collector.build_handoff_command(
            [{"cid": "c1", "text": "hello", "nickname": "Alice", "uid": "u1"}],
            "https://www.douyin.com/video/123", "123", "cmd-1",
        )
        self.assertEqual(command["command_id"], "cmd-1")
        self.assertEqual(command["targets"][0]["comment_id"], "c1")
        self.assertEqual(command["targets"][0]["comment_text"], "hello")

    def test_comment_row_has_required_profile_metrics(self):
        row = collector.comment_row({"text": "自然评论", "user": {"nickname": "小雨"}}, 1)
        self.assertEqual("小雨", row["nickname"])
        self.assertIn("follower_count", row)
        self.assertIn("favoriting_count", row)
        self.assertIn("total_favorited", row)

    def test_public_profile_reads_fans_and_likes(self):
        profile = collector.public_profile({"follower_count": 123, "favoriting_count": 45, "total_favorited": 456})
        self.assertEqual(123, profile["follower_count"])
        self.assertEqual(45, profile["favoriting_count"])
        self.assertEqual(456, profile["total_favorited"])

    def test_deduplicate_rows_prefers_first_comment_id(self):
        rows = collector.deduplicate_rows([
            {"cid": "c1", "text": "第一条"},
            {"cid": "c1", "text": "重复"},
            {"cid": "c2", "text": "第二条"},
        ])
        self.assertEqual(["c1", "c2"], [row["cid"] for row in rows])


if __name__ == "__main__":
    unittest.main()
