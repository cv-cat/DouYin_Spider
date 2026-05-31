from datetime import UTC, datetime, timedelta
import csv
import pytest

from web.db import connect_db
from web.services.agent_acquisition_service import AgentAcquisitionService


class SyncTaskManager:
    def __init__(self):
        self.runtimes = {}
        self.counter = 0

    def submit(self, task_type, summary, runner):
        self.counter += 1
        runner()
        return f"task-{self.counter}"


class DummyCrawlService:
    def __init__(self):
        self.search_calls = []
        self.comment_calls = []
        self.now = datetime.now(UTC)

    def search_general(
        self,
        query,
        require_num,
        sort_type,
        publish_time,
        filter_duration="",
        search_range="",
        content_type="",
    ):
        self.search_calls.append((query, require_num, sort_type, publish_time, filter_duration))
        return [
            {
                "aweme_info": {
                    "aweme_id": "aweme-keep",
                    "desc": "三角洲护航来个陪玩",
                    "share_url": "https://www.douyin.com/video/aweme-keep",
                    "create_time": int((self.now - timedelta(hours=8)).timestamp()),
                    "statistics": {"comment_count": 9, "digg_count": 22},
                    "author": {
                        "uid": "author-1",
                        "sec_uid": "sec-author-1",
                        "nickname": "作者一",
                        "follower_count": 120,
                        "following_count": 15,
                        "aweme_count": 7,
                        "avatar_thumb": {"url_list": ["https://img.example.com/a.jpg"]},
                    },
                }
            },
            {
                "aweme_info": {
                    "aweme_id": "aweme-low-comment",
                    "desc": "评论不足",
                    "create_time": int((self.now - timedelta(hours=8)).timestamp()),
                    "statistics": {"comment_count": 1},
                    "author": {"uid": "author-2", "nickname": "作者二"},
                }
            },
            {
                "aweme_info": {
                    "aweme_id": "aweme-old",
                    "desc": "旧作品",
                    "create_time": int((self.now - timedelta(days=9)).timestamp()),
                    "statistics": {"comment_count": 12},
                    "author": {"uid": "author-3", "nickname": "作者三"},
                }
            },
        ]

    def invoke(self, operation, payload):
        assert operation == "get_work_out_comment"
        self.comment_calls.append((payload["work_url"], payload.get("cursor", "0")))
        if payload.get("cursor", "0") != "0":
            return {"comments": [], "cursor": payload.get("cursor", "0"), "has_more": 0}
        return {
            "comments": [
                {
                    "cid": "comment-keep",
                    "aweme_id": "aweme-keep",
                    "text": "三角洲求带，来个陪玩",
                    "create_time": int((self.now - timedelta(minutes=30)).timestamp()),
                    "user": {
                        "uid": "user-1",
                        "sec_uid": "sec-user-1",
                        "nickname": "目标用户",
                        "follower_count": 277,
                        "following_count": 465,
                        "aweme_count": 0,
                    },
                },
                {
                    "cid": "comment-excluded",
                    "aweme_id": "aweme-keep",
                    "text": "电竞俱乐部招人",
                    "create_time": int((self.now - timedelta(minutes=20)).timestamp()),
                    "user": {"uid": "user-2", "nickname": "排除用户"},
                },
                {
                    "cid": "comment-old",
                    "aweme_id": "aweme-keep",
                    "text": "三角洲求带，三天前",
                    "create_time": int((self.now - timedelta(days=3)).timestamp()),
                    "user": {"uid": "user-3", "nickname": "旧评论用户"},
                },
            ],
            "cursor": "2",
            "has_more": 1,
        }


class DummyIMService:
    def __init__(self):
        self.created = []
        self.sent = []
        self.started = 0
        self.stopped = 0

    def create_conversation(self, to_user_id):
        self.created.append(str(to_user_id))
        return {
            "conversation_id": f"conversation-{to_user_id}",
            "conversation_short_id": f"short-{to_user_id}",
            "ticket": f"ticket-{to_user_id}",
        }

    def send_message(self, conversation_id, conversation_short_id, ticket, content):
        self.sent.append((conversation_id, conversation_short_id, ticket, content))
        return {"detail": {"status": "ok"}}

    def start_receiver(self):
        self.started += 1

    def stop_receiver(self):
        self.stopped += 1


def test_video_collection_filters_and_exports(tmp_path):
    service = AgentAcquisitionService(tmp_path / "web-ui.sqlite3", tmp_path / "runtime", SyncTaskManager(), DummyCrawlService())
    service.save_video_config(
        {
            "keywords": "三角洲护航",
            "collect_count": "5",
            "comment_count_min": "3",
            "recent_days": "2",
            "sort_type": "0",
            "publish_time": "0",
            "filter_duration": "",
        }
    )

    payload = service.queue_video_collect()

    rows = service.list_videos()
    assert payload["task_id"] == "task-1"
    assert len(rows) == 1
    assert rows[0]["aweme_id"] == "aweme-keep"
    assert rows[0]["keyword"] == "三角洲护航"
    assert rows[0]["nickname"] == "作者一"
    assert rows[0]["comment_count"] == 9

    export_path = service.export_videos()
    with export_path.open(newline="", encoding="utf-8-sig") as handle:
        exported = list(csv.DictReader(handle))
    assert exported[0]["aweme_id"] == "aweme-keep"
    assert exported[0]["nickname"] == "作者一"


def test_comment_monitor_filters_recent_intent_and_exports(tmp_path):
    crawl = DummyCrawlService()
    service = AgentAcquisitionService(tmp_path / "web-ui.sqlite3", tmp_path / "runtime", SyncTaskManager(), crawl)
    service.save_comment_config(
        {
            "video_ids": "aweme-keep",
            "monitor_minutes": "180",
            "date_from": "",
            "date_to": "",
            "page_count": "3",
            "thread_count": "20",
            "interval_minutes": "1",
            "include_keywords": "来,价,陪,下,求带",
            "exclude_keywords": "电竞,俱乐部",
            "only_intent": "on",
            "fetch_first_level": "on",
            "enterprise_webhook": "",
            "proxy_url": "",
        }
    )

    result = service.collect_comment_cycle()

    rows = service.list_comments()
    assert result["inserted_count"] == 1
    assert len(rows) == 1
    assert rows[0]["comment_id"] == "comment-keep"
    assert rows[0]["nickname"] == "目标用户"
    assert rows[0]["grade"] in {"S", "A"}
    assert rows[0]["is_intent"] == 1
    assert rows[0]["comment_time_label"]

    export_path = service.export_comments()
    with export_path.open(newline="", encoding="utf-8-sig") as handle:
        exported = list(csv.DictReader(handle))
    assert exported[0]["comment_id"] == "comment-keep"
    assert exported[0]["nickname"] == "目标用户"


def test_private_queue_imports_uids_and_sends_text(tmp_path):
    im_service = DummyIMService()
    service = AgentAcquisitionService(
        tmp_path / "web-ui.sqlite3",
        tmp_path / "runtime",
        SyncTaskManager(),
        DummyCrawlService(),
        im_service=im_service,
    )
    service.save_private_config(
        {
            "message_text": "你好，看到你在找三角洲陪玩，可以先了解需求。",
            "send_interval_seconds": "0",
            "send_mode": "text",
            "proxy_api": "",
            "auto_refresh_minutes": "60",
        }
    )
    imported = service.import_private_uids("101295715164\n711342044613\n101295715164")

    result = service.send_private_batch(limit=10)

    rows = service.list_private_targets()
    assert imported["imported_count"] == 2
    assert result["sent_count"] == 2
    assert [row["status"] for row in rows] == ["sent", "sent"]
    assert im_service.created == ["101295715164", "711342044613"]
    assert im_service.sent[0][3] == "你好，看到你在找三角洲陪玩，可以先了解需求。"


def test_private_send_rejects_unsupported_card_mode(tmp_path):
    im_service = DummyIMService()
    service = AgentAcquisitionService(
        tmp_path / "web-ui.sqlite3",
        tmp_path / "runtime",
        SyncTaskManager(),
        DummyCrawlService(),
        im_service=im_service,
    )
    service.save_private_config(
        {
            "message_text": "文字内容",
            "send_interval_seconds": "0",
            "send_mode": "card",
            "card_payload": "{\"title\":\"卡片\"}",
        }
    )
    service.import_private_uids("101295715164")

    with pytest.raises(RuntimeError, match="只支持文本私信"):
        service.send_private_batch(limit=1)

    rows = service.list_private_targets()
    assert rows[0]["status"] == "pending"
    assert im_service.created == []
    assert im_service.sent == []


def test_group_monitor_uses_im_receiver_and_lists_events(tmp_path):
    im_service = DummyIMService()
    db_path = tmp_path / "web-ui.sqlite3"
    service = AgentAcquisitionService(
        db_path,
        tmp_path / "runtime",
        SyncTaskManager(),
        DummyCrawlService(),
        im_service=im_service,
    )
    with connect_db(db_path) as conn:
        conn.execute(
            "insert into event_feed(channel, event_type, payload, created_at) values(?, ?, ?, ?)",
            (
                "im",
                "text",
                '{"channel":"im","payload":{"event_type":"text","conversation_id":"group-1","user":{"uid":"u1","nickname":"群用户"},"content":"三角洲求带"}}',
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()

    start_result = service.start_group_monitor()
    rows = service.list_group_messages()
    export_path = service.export_group_messages()
    stop_result = service.stop_group_monitor()

    assert start_result == {"message": "群聊监控已启动"}
    assert stop_result == {"message": "群聊监控已停止"}
    assert im_service.started == 1
    assert im_service.stopped == 1
    assert rows[0]["group_id"] == "group-1"
    assert rows[0]["nickname"] == "群用户"
    assert rows[0]["user_id"] == "u1"
    assert rows[0]["content"] == "三角洲求带"
    with export_path.open(newline="", encoding="utf-8-sig") as handle:
        exported = list(csv.DictReader(handle))
    assert exported[0]["group_id"] == "group-1"
