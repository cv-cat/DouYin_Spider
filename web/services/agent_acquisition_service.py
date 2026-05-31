from datetime import UTC, datetime, timedelta
import csv
import json
from pathlib import Path
import re
import threading
import time

import requests

from web.db import connect_db, init_db
from web.services.lead_scoring_service import LeadScoringService


class AgentAcquisitionService:
    VIDEO_RUNTIME_KEY = "agent:video"
    COMMENT_RUNTIME_KEY = "agent:comments"
    PRIVATE_RUNTIME_KEY = "agent:private"
    GROUP_RUNTIME_KEY = "agent:groups"

    DEFAULT_VIDEO_CONFIG = {
        "keywords": "三角洲陪玩、三角洲带玩",
        "collect_count": "0",
        "comment_count_min": "0",
        "recent_days": "0",
        "sort_type": "0",
        "publish_time": "0",
        "filter_duration": "",
        "intercept": "on",
    }
    DEFAULT_COMMENT_CONFIG = {
        "video_ids": "",
        "monitor_minutes": "180",
        "date_from": "",
        "date_to": "",
        "page_count": "3",
        "thread_count": "20",
        "interval_minutes": "1",
        "include_keywords": "来,价,陪,下=,求带,找陪,护航,绿护,纯绿护",
        "exclude_keywords": "电竞,俱乐部,哥,雾",
        "only_intent": "on",
        "fetch_first_level": "on",
        "enterprise_webhook": "",
        "proxy_url": "",
        "auto_to_private": "",
    }
    DEFAULT_PRIVATE_CONFIG = {
        "proxy_api": "",
        "auto_refresh_minutes": "60",
        "send_mode": "text",
        "send_interval_seconds": "10",
        "message_text": "",
        "card_payload": "",
        "proxy_url": "",
        "headless_mode": "",
        "batch_size": "5",
        "batch_pause_minutes": "10",
        "daily_limit": "0",
        "active_hours": "",
    }
    DEFAULT_LIVE_CONFIG = {
        "live_ids": "",
    }
    DEFAULT_GROUP_CONFIG = {
        "group_ids": "",
        "include_keywords": "",
        "exclude_keywords": "",
        "interval_seconds": "1",
    }

    def __init__(
        self,
        db_path,
        runtime_dir,
        task_manager,
        crawl_service,
        scoring_service=None,
        im_service=None,
        live_service=None,
    ):
        self.db_path = db_path
        self.runtime_dir = Path(runtime_dir)
        self.task_manager = task_manager
        self.crawl_service = crawl_service
        self.scoring_service = scoring_service or LeadScoringService()
        self.im_service = im_service
        self.live_service = live_service
        with connect_db(self.db_path) as conn:
            init_db(conn)

    def save_video_config(self, values):
        return self._save_config("video", self.DEFAULT_VIDEO_CONFIG, values)

    def get_video_config(self):
        return self._get_config("video", self.DEFAULT_VIDEO_CONFIG)

    def queue_video_collect(self):
        stop_event = threading.Event()
        self.task_manager.runtimes[self.VIDEO_RUNTIME_KEY] = stop_event

        def runner():
            try:
                return self._collect_videos(stop_event)
            finally:
                self.task_manager.runtimes.pop(self.VIDEO_RUNTIME_KEY, None)

        task_id = self.task_manager.submit("agent.video_collect", "视频采集", runner)
        return {"task_id": task_id}

    def start_video_collect(self):
        return self.queue_video_collect()

    def stop_video_collect(self):
        event = self.task_manager.runtimes.get(self.VIDEO_RUNTIME_KEY)
        if event:
            event.set()
        return {"message": "视频采集已停止"}

    def clear_videos(self):
        with connect_db(self.db_path) as conn:
            count = conn.execute("select count(*) as c from agent_video_items").fetchone()["c"]
            conn.execute("delete from agent_video_items")
            conn.commit()
        return {"cleared_count": int(count or 0)}

    def list_videos(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute("select * from agent_video_items order by id asc").fetchall()
        return [self._decorate_video(dict(row)) for row in rows]

    def export_videos(self):
        rows = self.list_videos()
        path = self._runtime_path("agent-videos")
        headers = [
            "id",
            "keyword",
            "aweme_id",
            "title",
            "nickname",
            "user_id",
            "sec_uid",
            "comment_count",
            "follower_count",
            "following_count",
            "aweme_count",
            "share_url",
        ]
        self._write_csv(path, headers, rows)
        return path

    def video_status(self):
        running = self.VIDEO_RUNTIME_KEY in self.task_manager.runtimes
        return {"running": running, "label": "正在采集" if running else "采集已停止"}

    def save_comment_config(self, values):
        return self._save_config("comments", self.DEFAULT_COMMENT_CONFIG, values)

    def get_comment_config(self):
        return self._get_config("comments", self.DEFAULT_COMMENT_CONFIG)

    def queue_comment_monitor(self):
        stop_event = threading.Event()
        self.task_manager.runtimes[self.COMMENT_RUNTIME_KEY] = stop_event
        self._comment_monitor_state = {"rounds": 0, "total_inserted": 0, "last_inserted": 0, "last_scanned": 0, "next_scan_ts": 0}

        def runner():
            try:
                total_inserted = 0
                rounds = 0
                while not stop_event.is_set():
                    rounds += 1
                    result = self.collect_comment_cycle()
                    inserted = int(result["inserted_count"])
                    total_inserted += inserted
                    interval = max(self._int_value(self.get_comment_config().get("interval_minutes"), 1), 1) * 60
                    self._comment_monitor_state = {
                        "rounds": rounds,
                        "total_inserted": total_inserted,
                        "last_inserted": inserted,
                        "last_scanned": int(result.get("scanned_count", 0)),
                        "next_scan_ts": time.time() + interval,
                    }
                    if stop_event.wait(interval):
                        break
                return {"inserted_count": total_inserted}
            finally:
                self.task_manager.runtimes.pop(self.COMMENT_RUNTIME_KEY, None)
                self._comment_monitor_state = None

        task_id = self.task_manager.submit("agent.comment_monitor", "评论监控", runner)
        return {"task_id": task_id}

    def start_comment_monitor(self):
        return self.queue_comment_monitor()

    def stop_comment_monitor(self):
        event = self.task_manager.runtimes.get(self.COMMENT_RUNTIME_KEY)
        if event:
            event.set()
        return {"message": "评论监控已停止"}

    def collect_comment_cycle(self):
        config = self.get_comment_config()
        aweme_ids = self._split_lines(config.get("video_ids"))
        include_terms = self._split_terms(config.get("include_keywords"))
        exclude_terms = self._split_terms(config.get("exclude_keywords"))
        page_count = self._int_value(config.get("page_count"), 3)
        cutoff = self._comment_cutoff(config)
        inserted = 0
        scanned = 0
        for aweme_id in aweme_ids:
            comments = self._fetch_comment_pages(aweme_id, page_count)
            for comment in comments:
                scanned += 1
                if not self._comment_in_time_range(comment, cutoff, config):
                    continue
                text = str(comment.get("text") or "")
                if include_terms and not self._contains_any(text, include_terms):
                    continue
                if exclude_terms and self._contains_any(text, exclude_terms):
                    continue
                item = self._build_comment_item(aweme_id, comment)
                if self._checkbox_on(config.get("only_intent")) and not item["is_intent"]:
                    continue
                inserted += self._insert_comment_item(item)
                if item["is_intent"]:
                    self._push_webhook(config.get("enterprise_webhook"), item)
                    if self._checkbox_on(config.get("auto_to_private")):
                        self._add_private_target(item.get("user_id"))
        return {"scanned_count": scanned, "inserted_count": inserted}

    def _add_private_target(self, uid):
        uid = str(uid or "").strip()
        if not uid:
            return
        with connect_db(self.db_path) as conn:
            conn.execute(
                "insert into agent_private_targets(uid, status, ip, error_message, created_at, sent_at) "
                "values(?, 'pending', '', '', ?, null) on conflict(uid) do nothing",
                (uid, self._now()),
            )
            conn.commit()

    def clear_comments(self):
        with connect_db(self.db_path) as conn:
            count = conn.execute("select count(*) as c from agent_comment_items").fetchone()["c"]
            conn.execute("delete from agent_comment_items")
            conn.commit()
        return {"cleared_count": int(count or 0)}

    def list_comments(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute("select * from agent_comment_items order by id asc").fetchall()
        return [self._decorate_comment(dict(row)) for row in rows]

    def export_comments(self, rows=None):
        rows = self.list_comments() if rows is None else rows
        path = self._runtime_path("agent-comments")
        headers = [
            "id",
            "aweme_id",
            "comment_id",
            "nickname",
            "user_id",
            "sec_uid",
            "blue_v",
            "follower_count",
            "following_count",
            "aweme_count",
            "comment_text",
            "grade",
            "score",
            "comment_time_label",
        ]
        self._write_csv(path, headers, rows)
        return path

    def comment_status(self):
        running = self.COMMENT_RUNTIME_KEY in self.task_manager.runtimes
        state = getattr(self, "_comment_monitor_state", None)
        if running and state and state.get("next_scan_ts"):
            remain = max(0, int(state["next_scan_ts"] - time.time()))
            label = (
                f"🟢 监控中：已扫 {state['rounds']} 轮 · 本轮新增 {state['last_inserted']} 条"
                f"（扫描 {state['last_scanned']}）· 下次 {remain}s 后"
            )
        elif running:
            label = "🟢 监控中：正在扫描…"
        else:
            label = "监控已停止"
        return {"running": running, "label": label}

    def save_private_config(self, values):
        return self._save_config("private", self.DEFAULT_PRIVATE_CONFIG, values)

    def get_private_config(self):
        return self._get_config("private", self.DEFAULT_PRIVATE_CONFIG)

    def import_private_uids(self, uid_text):
        uids = []
        for token in re.split(r"[\s,，]+", str(uid_text or "")):
            value = token.strip()
            if value:
                uids.append(value)
        imported = 0
        now = self._now()
        with connect_db(self.db_path) as conn:
            for uid in dict.fromkeys(uids):
                cursor = conn.execute(
                    "insert into agent_private_targets(uid, status, ip, error_message, created_at, sent_at) "
                    "values(?, 'pending', '', '', ?, null) on conflict(uid) do nothing",
                    (uid, now),
                )
                imported += cursor.rowcount
            conn.commit()
        return {"imported_count": imported}

    def queue_private_send(self):
        stop_event = threading.Event()
        self.task_manager.runtimes[self.PRIVATE_RUNTIME_KEY] = stop_event

        def runner():
            try:
                return self.send_private_batch(stop_event=stop_event)
            finally:
                self.task_manager.runtimes.pop(self.PRIVATE_RUNTIME_KEY, None)

        task_id = self.task_manager.submit("agent.private_send", "私信发送", runner)
        return {"task_id": task_id}

    def start_private_send(self):
        return self.queue_private_send()

    def stop_private_send(self):
        event = self.task_manager.runtimes.get(self.PRIVATE_RUNTIME_KEY)
        if event:
            event.set()
        return {"message": "私信发送已停止"}

    def send_private_batch(self, limit=0, stop_event=None):
        if self.im_service is None:
            raise RuntimeError("IM service is not configured")
        config = self.get_private_config()
        send_mode = str(config.get("send_mode") or "text").strip().lower()
        if send_mode not in {"", "text"}:
            raise RuntimeError("当前底层只支持文本私信，卡片模式未接入 DouyinAPI")
        message = str(config.get("message_text") or "").strip()
        if not message:
            raise RuntimeError("私信文本为空")
        interval = max(self._int_value(config.get("send_interval_seconds"), 10), 0)
        with connect_db(self.db_path) as conn:
            query = "select * from agent_private_targets where status = 'pending' order by id asc"
            params = ()
            if limit:
                query += " limit ?"
                params = (int(limit),)
            rows = [dict(row) for row in conn.execute(query, params).fetchall()]
        sent = 0
        for row in rows:
            if stop_event and stop_event.is_set():
                break
            try:
                conversation = self.im_service.create_conversation(row["uid"])
                self.im_service.send_message(
                    conversation["conversation_id"],
                    conversation["conversation_short_id"],
                    conversation["ticket"],
                    message,
                )
                self._mark_private_target(row["id"], "sent", "")
                sent += 1
            except Exception as exc:
                self._mark_private_target(row["id"], "failed", f"{type(exc).__name__}: {exc}")
            if interval and (not stop_event or not stop_event.is_set()):
                time.sleep(interval)
        return {"sent_count": sent}

    def test_private_connection(self, uid=None):
        """只创建会话验证登录态与接口连通，不发送任何消息内容（对方不会收到消息）。"""
        if self.im_service is None:
            raise RuntimeError("IM service is not configured")
        auth = self.im_service._auth()
        if not getattr(auth, "ticket", None):
            raise RuntimeError(
                "私信登录态缺少 ticket（bd-ticket-guard 票据）。\n"
                "当前 cookie 可用于视频采集和评论监控，但私信走 imapi 协议，"
                "额外需要 ticket；项目登录流程当前未获取该票据"
                "（dyGenerateInitData 中读取 web_protect 的代码被禁用），"
                "因此私信暂时无法发送。"
            )
        if not uid:
            with connect_db(self.db_path) as conn:
                row = conn.execute(
                    "select uid from agent_private_targets order by id asc limit 1"
                ).fetchone()
            if not row:
                raise RuntimeError("私信列表为空，请先添加目标")
            uid = row["uid"]
        conversation = self.im_service.create_conversation(uid)
        return {"ok": True, "uid": uid, "conversation_id": conversation.get("conversation_id")}

    def clear_private_targets(self):
        with connect_db(self.db_path) as conn:
            count = conn.execute("select count(*) as c from agent_private_targets").fetchone()["c"]
            conn.execute("delete from agent_private_targets")
            conn.commit()
        return {"cleared_count": int(count or 0)}

    def list_private_targets(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute("select * from agent_private_targets order by id asc").fetchall()
            result = []
            for row in rows:
                target = dict(row)
                comment = conn.execute(
                    "select nickname, comment_text, create_time, grade, score, sec_uid "
                    "from agent_comment_items where user_id = ? order by id desc limit 1",
                    (target["uid"],),
                ).fetchone()
                if comment:
                    target["nickname"] = comment["nickname"]
                    target["comment_text"] = comment["comment_text"]
                    target["comment_time_label"] = self._time_label(comment["create_time"])
                    target["grade"] = comment["grade"]
                    target["score"] = comment["score"]
                    sec_uid = comment["sec_uid"] or ""
                    target["sec_uid"] = sec_uid
                    target["profile_url"] = f"https://www.douyin.com/user/{sec_uid}" if sec_uid else ""
                else:
                    target["nickname"] = ""
                    target["comment_text"] = ""
                    target["comment_time_label"] = ""
                    target["grade"] = ""
                    target["score"] = ""
                    target["sec_uid"] = ""
                    target["profile_url"] = ""
                result.append(target)
        return result

    def export_private_targets(self):
        rows = self.list_private_targets()
        path = self._runtime_path("agent-private-targets")
        headers = [
            "id", "uid", "nickname", "profile_url", "comment_text", "comment_time_label",
            "grade", "score", "status", "ip", "error_message", "created_at", "sent_at",
        ]
        self._write_csv(path, headers, rows)
        return path

    def private_status(self):
        running = self.PRIVATE_RUNTIME_KEY in self.task_manager.runtimes
        return {"running": running, "label": "发送中" if running else "发送已停止"}

    def save_group_config(self, values):
        return self._save_config("groups", self.DEFAULT_GROUP_CONFIG, values)

    def get_group_config(self):
        return self._get_config("groups", self.DEFAULT_GROUP_CONFIG)

    def start_group_monitor(self):
        if self.im_service is None:
            raise RuntimeError("IM service is not configured")
        self.im_service.start_receiver()
        self.task_manager.runtimes[self.GROUP_RUNTIME_KEY] = True
        return {"message": "群聊监控已启动"}

    def queue_group_monitor(self):
        return self.start_group_monitor()

    def stop_group_monitor(self):
        if self.im_service is None:
            raise RuntimeError("IM service is not configured")
        self.im_service.stop_receiver()
        self.task_manager.runtimes.pop(self.GROUP_RUNTIME_KEY, None)
        return {"message": "群聊监控已停止"}

    def clear_group_messages(self):
        with connect_db(self.db_path) as conn:
            count = conn.execute("select count(*) as c from event_feed where channel = 'im'").fetchone()["c"]
            conn.execute("delete from event_feed where channel = 'im'")
            conn.commit()
        return {"cleared_count": int(count or 0)}

    def list_group_messages(self, limit=200):
        config = self.get_group_config()
        group_ids = set(self._split_lines(config.get("group_ids")))
        include_terms = self._split_terms(config.get("include_keywords"))
        exclude_terms = self._split_terms(config.get("exclude_keywords"))
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                "select * from event_feed where channel = 'im' order by id desc limit ?",
                (max(int(limit or 200), 1),),
            ).fetchall()
        messages = []
        for row in rows:
            message = self._decorate_group_event(dict(row))
            content = str(message.get("content") or "")
            if group_ids and message.get("group_id") not in group_ids:
                continue
            if include_terms and not self._contains_any(content, include_terms):
                continue
            if exclude_terms and self._contains_any(content, exclude_terms):
                continue
            messages.append(message)
        return messages

    def export_group_messages(self):
        rows = self.list_group_messages()
        path = self._runtime_path("agent-group-messages")
        headers = ["id", "created_at", "group_id", "nickname", "user_id", "content", "status"]
        self._write_csv(path, headers, rows)
        return path

    def group_status(self):
        running = self.GROUP_RUNTIME_KEY in self.task_manager.runtimes or "im:default" in self.task_manager.runtimes
        return {"running": running, "label": "群聊监控中" if running else "群聊监控已停止"}

    def save_live_config(self, values):
        config = self._save_config("live", self.DEFAULT_LIVE_CONFIG, values)
        self.import_live_rooms(config.get("live_ids", ""))
        return config

    def get_live_config(self):
        return self._get_config("live", self.DEFAULT_LIVE_CONFIG)

    def import_live_rooms(self, live_text):
        imported = 0
        now = self._now()
        with connect_db(self.db_path) as conn:
            for live_id in dict.fromkeys(self._extract_live_ids(live_text)):
                cursor = conn.execute(
                    "insert into agent_live_rooms(live_id, title, status, online_text, created_at, updated_at) "
                    "values(?, '', 'pending', '', ?, ?) on conflict(live_id) do nothing",
                    (live_id, now, now),
                )
                imported += cursor.rowcount
            conn.commit()
        return {"imported_count": imported}

    def list_live_rooms(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute("select * from agent_live_rooms order by id asc").fetchall()
        return [dict(row) for row in rows]

    def start_all_live_rooms(self):
        if self.live_service is None:
            raise RuntimeError("Live service is not configured")
        started = 0
        now = self._now()
        with connect_db(self.db_path) as conn:
            rows = conn.execute("select * from agent_live_rooms order by id asc").fetchall()
            for row in rows:
                self.live_service.start_listener(row["live_id"])
                conn.execute(
                    "update agent_live_rooms set status = 'monitoring', updated_at = ? where live_id = ?",
                    (now, row["live_id"]),
                )
                started += 1
            conn.commit()
        return {"started_count": started}

    def start_live_monitor(self):
        return self.start_all_live_rooms()

    def stop_all_live_rooms(self):
        if self.live_service is None:
            raise RuntimeError("Live service is not configured")
        stopped = 0
        now = self._now()
        with connect_db(self.db_path) as conn:
            rows = conn.execute("select * from agent_live_rooms order by id asc").fetchall()
            for row in rows:
                self.live_service.stop_listener(row["live_id"])
                conn.execute(
                    "update agent_live_rooms set status = 'stopped', updated_at = ? where live_id = ?",
                    (now, row["live_id"]),
                )
                stopped += 1
            conn.commit()
        return {"stopped_count": stopped}

    def stop_live_monitor(self):
        return self.stop_all_live_rooms()

    def clear_live_rooms(self):
        with connect_db(self.db_path) as conn:
            count = conn.execute("select count(*) as c from agent_live_rooms").fetchone()["c"]
            conn.execute("delete from agent_live_rooms")
            conn.execute("delete from event_feed where channel = 'live'")
            conn.commit()
        return {"cleared_count": int(count or 0)}

    def export_live_rooms(self):
        rows = self.list_live_rooms()
        path = self._runtime_path("agent-live-rooms")
        headers = ["id", "live_id", "title", "status", "online_text", "created_at", "updated_at"]
        self._write_csv(path, headers, rows)
        return path

    def list_live_events(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                "select * from event_feed where channel = 'live' order by id desc limit 200"
            ).fetchall()
        return [self._decorate_live_event(dict(row)) for row in rows]

    def _collect_videos(self, stop_event):
        config = self.get_video_config()
        keywords = self._split_lines(config.get("keywords"))
        target = self._int_value(config.get("collect_count"), 0)
        target = target if target > 0 else 20
        inserted = 0
        for keyword in keywords:
            if stop_event.is_set():
                break
            items = self.crawl_service.search_general(
                keyword,
                str(target),
                str(config.get("sort_type") or "0"),
                str(config.get("publish_time") or "0"),
                str(config.get("filter_duration") or ""),
            )
            for item in items:
                if stop_event.is_set():
                    break
                video = self._build_video_item(keyword, item)
                if not self._video_passes_filters(video, config):
                    continue
                inserted += self._insert_video_item(video)
        return {"inserted_count": inserted}

    def _extract_live_ids(self, live_text):
        ids = []
        for token in re.split(r"[\s,，]+", str(live_text or "")):
            value = token.strip()
            if not value:
                continue
            if "/" in value:
                value = value.rstrip("/").split("/")[-1]
            if value:
                ids.append(value)
        return ids

    def _decorate_live_event(self, row):
        payload = {}
        try:
            payload = json.loads(row.get("payload") or "{}")
        except Exception:
            payload = {}
        body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        row["room_id"] = payload.get("room_id") or body.get("room_id") or "-"
        row["event_label"] = body.get("event_type") or payload.get("event_type") or "-"
        row["user"] = body.get("user") or body.get("nickname") or "-"
        row["content"] = body.get("content") or body.get("gift") or json.dumps(body, ensure_ascii=False)
        return row

    def _decorate_group_event(self, row):
        payload = {}
        try:
            payload = json.loads(row.get("payload") or "{}")
        except Exception:
            payload = {}
        body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        user = body.get("user") if isinstance(body.get("user"), dict) else {}
        content = body.get("content") or body.get("text") or body.get("message") or body.get("msg")
        if not isinstance(content, str):
            content = json.dumps(content if content else body, ensure_ascii=False)
        row["group_id"] = str(
            body.get("group_id")
            or body.get("conversation_id")
            or body.get("conversation_short_id")
            or body.get("room_id")
            or "-"
        )
        row["nickname"] = str(body.get("nickname") or user.get("nickname") or "-")
        row["user_id"] = str(body.get("user_id") or body.get("uid") or user.get("uid") or user.get("user_id") or "-")
        row["content"] = content
        row["status"] = str(body.get("event_type") or row.get("event_type") or "-")
        return row

    def _build_video_item(self, keyword, item):
        aweme = item.get("aweme_info") or item
        author = aweme.get("author") or {}
        stats = aweme.get("statistics") or {}
        avatar_thumb = author.get("avatar_thumb") or {}
        avatar_list = avatar_thumb.get("url_list") or []
        return {
            "keyword": keyword,
            "aweme_id": str(aweme.get("aweme_id") or ""),
            "title": str(aweme.get("desc") or ""),
            "nickname": str(author.get("nickname") or ""),
            "user_id": str(author.get("uid") or author.get("user_id") or ""),
            "sec_uid": str(author.get("sec_uid") or ""),
            "avatar_url": avatar_list[0] if avatar_list else "",
            "share_url": str(aweme.get("share_url") or self._work_url(aweme.get("aweme_id"))),
            "comment_count": self._int_value(stats.get("comment_count"), 0),
            "follower_count": self._int_value(author.get("follower_count"), 0),
            "following_count": self._int_value(author.get("following_count"), 0),
            "aweme_count": self._int_value(author.get("aweme_count"), 0),
            "digg_count": self._int_value(stats.get("digg_count"), 0),
            "create_time": self._int_value(aweme.get("create_time"), 0),
            "raw_payload": json.dumps(item, ensure_ascii=False),
        }

    def _video_passes_filters(self, video, config):
        if not video["aweme_id"]:
            return False
        if video["comment_count"] < self._int_value(config.get("comment_count_min"), 0):
            return False
        recent_days = self._int_value(config.get("recent_days"), 0)
        if recent_days > 0 and video["create_time"]:
            cutoff = datetime.now(UTC) - timedelta(days=recent_days)
            if datetime.fromtimestamp(video["create_time"], UTC) < cutoff:
                return False
        return True

    def _insert_video_item(self, video):
        with connect_db(self.db_path) as conn:
            cursor = conn.execute(
                "insert into agent_video_items("
                "keyword, aweme_id, title, nickname, user_id, sec_uid, avatar_url, share_url, comment_count, "
                "follower_count, following_count, aweme_count, digg_count, create_time, raw_payload, created_at"
                ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "on conflict(keyword, aweme_id) do update set "
                "title=excluded.title, nickname=excluded.nickname, user_id=excluded.user_id, sec_uid=excluded.sec_uid, "
                "avatar_url=excluded.avatar_url, share_url=excluded.share_url, comment_count=excluded.comment_count, "
                "follower_count=excluded.follower_count, following_count=excluded.following_count, aweme_count=excluded.aweme_count, "
                "digg_count=excluded.digg_count, create_time=excluded.create_time, raw_payload=excluded.raw_payload",
                (
                    video["keyword"],
                    video["aweme_id"],
                    video["title"],
                    video["nickname"],
                    video["user_id"],
                    video["sec_uid"],
                    video["avatar_url"],
                    video["share_url"],
                    video["comment_count"],
                    video["follower_count"],
                    video["following_count"],
                    video["aweme_count"],
                    video["digg_count"],
                    video["create_time"],
                    video["raw_payload"],
                    self._now(),
                ),
            )
            conn.commit()
        return max(cursor.rowcount, 0)

    def _fetch_comment_pages(self, aweme_id, page_count):
        cursor = "0"
        pages = 0
        comments = []
        limit = page_count if page_count > 0 else 999999
        while pages < limit:
            payload = self.crawl_service.invoke(
                "get_work_out_comment",
                {"work_url": self._work_url(aweme_id), "cursor": cursor},
            )
            page_comments = payload.get("comments") or payload.get("data") or []
            if not page_comments:
                break
            comments.extend(page_comments)
            pages += 1
            if payload.get("has_more") != 1:
                break
            next_cursor = str(payload.get("cursor") or payload.get("next_cursor") or "")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return comments

    def _build_comment_item(self, aweme_id, comment):
        user = comment.get("user") or {}
        text = str(comment.get("text") or "")
        scoring = self.scoring_service.score_lead(
            {
                "source_type": "comment",
                "content": text,
                "comment_text": text,
                "nickname": str(user.get("nickname") or ""),
                "signature": str(user.get("signature") or ""),
            }
        )
        grade = scoring["grade"]
        return {
            "aweme_id": str(comment.get("aweme_id") or aweme_id),
            "comment_id": str(comment.get("cid") or comment.get("comment_id") or ""),
            "user_id": str(user.get("uid") or user.get("user_id") or ""),
            "sec_uid": str(user.get("sec_uid") or ""),
            "nickname": str(user.get("nickname") or ""),
            "blue_v": "是" if self._is_blue_v(user) else "否",
            "follower_count": self._int_value(user.get("follower_count"), 0),
            "following_count": self._int_value(user.get("following_count"), 0),
            "aweme_count": self._int_value(user.get("aweme_count"), 0),
            "comment_text": text,
            "create_time": self._int_value(comment.get("create_time"), 0),
            "score": int(scoring["total_score"]),
            "grade": grade,
            "is_intent": 1 if grade in {"S", "A"} and not scoring["excluded"] else 0,
            "matched_signals": json.dumps(scoring["matched_terms"], ensure_ascii=False),
            "raw_payload": json.dumps(comment, ensure_ascii=False),
        }

    def _insert_comment_item(self, item):
        if not item["aweme_id"] or not item["comment_id"]:
            return 0
        with connect_db(self.db_path) as conn:
            cursor = conn.execute(
                "insert into agent_comment_items("
                "aweme_id, comment_id, user_id, sec_uid, nickname, blue_v, follower_count, following_count, aweme_count, "
                "comment_text, create_time, score, grade, is_intent, matched_signals, raw_payload, created_at"
                ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "on conflict(aweme_id, comment_id) do nothing",
                (
                    item["aweme_id"],
                    item["comment_id"],
                    item["user_id"],
                    item["sec_uid"],
                    item["nickname"],
                    item["blue_v"],
                    item["follower_count"],
                    item["following_count"],
                    item["aweme_count"],
                    item["comment_text"],
                    item["create_time"],
                    item["score"],
                    item["grade"],
                    item["is_intent"],
                    item["matched_signals"],
                    item["raw_payload"],
                    self._now(),
                ),
            )
            conn.commit()
        return cursor.rowcount

    def _mark_private_target(self, row_id, status, error_message):
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update agent_private_targets set status = ?, error_message = ?, sent_at = ? where id = ?",
                (status, error_message, self._now() if status == "sent" else None, row_id),
            )
            conn.commit()

    def _save_config(self, name, defaults, values):
        config = dict(defaults)
        for key in defaults:
            if key in values:
                config[key] = str(values.get(key) or "")
        now = self._now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "insert into agent_configs(config_key, value, updated_at) values(?, ?, ?) "
                "on conflict(config_key) do update set value=excluded.value, updated_at=excluded.updated_at",
                (name, json.dumps(config, ensure_ascii=False), now),
            )
            conn.commit()
        return config

    def _get_config(self, name, defaults):
        with connect_db(self.db_path) as conn:
            row = conn.execute("select value from agent_configs where config_key = ?", (name,)).fetchone()
        if not row:
            return dict(defaults)
        try:
            payload = json.loads(row["value"])
        except Exception:
            return dict(defaults)
        config = dict(defaults)
        if isinstance(payload, dict):
            config.update({key: str(value) for key, value in payload.items() if key in config})
        return config

    def _comment_cutoff(self, config):
        minutes = self._int_value(config.get("monitor_minutes"), 0)
        return datetime.now(UTC) - timedelta(minutes=minutes) if minutes > 0 else None

    def _comment_in_time_range(self, comment, cutoff, config):
        create_time = self._int_value(comment.get("create_time"), 0)
        if not create_time:
            return False
        created_at = datetime.fromtimestamp(create_time, UTC)
        date_from = str(config.get("date_from") or "").strip()
        date_to = str(config.get("date_to") or "").strip()
        if date_from and date_to:
            return date_from <= created_at.date().isoformat() <= date_to
        return created_at >= cutoff if cutoff else True

    def _decorate_video(self, row):
        row["create_time_label"] = self._time_label(row.get("create_time"))
        return row

    def _decorate_comment(self, row):
        row["comment_time_label"] = self._time_label(row.get("create_time"))
        return row

    def _runtime_path(self, prefix):
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return self.runtime_dir / f"{prefix}-{stamp}.csv"

    def _write_csv(self, path, headers, rows):
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in headers})

    def _split_lines(self, value):
        return [item.strip() for item in re.split(r"[\n,，、]+", str(value or "")) if item.strip()]

    def _split_terms(self, value):
        return [item.strip() for item in re.split(r"[\n,，、]+", str(value or "")) if item.strip()]

    def _contains_any(self, text, terms):
        return any(term and term in text for term in terms)

    def _checkbox_on(self, value):
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def _int_value(self, value, default=0):
        try:
            return int(str(value or "").strip())
        except (TypeError, ValueError):
            return default

    def _is_blue_v(self, user):
        return bool(user.get("enterprise_verify_reason") or user.get("custom_verify") or user.get("verification_type"))

    def _push_webhook(self, webhook, item):
        url = str(webhook or "").strip()
        if not url:
            return
        try:
            requests.post(
                url,
                json={"msgtype": "text", "text": {"content": f"{item['nickname']}：{item['comment_text']}"}},
                timeout=5,
            )
        except Exception:
            return

    def _work_url(self, aweme_id):
        aweme_id = str(aweme_id or "").strip()
        return f"https://www.douyin.com/video/{aweme_id}" if aweme_id else ""

    def _time_label(self, value):
        timestamp = self._int_value(value, 0)
        if not timestamp:
            return ""
        return datetime.fromtimestamp(timestamp, UTC).astimezone().strftime("%Y-%m-%d %H:%M")

    def _now(self):
        return datetime.now(UTC).isoformat()
