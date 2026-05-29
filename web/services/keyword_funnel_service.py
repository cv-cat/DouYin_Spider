from datetime import UTC, datetime
import json
import uuid

from web.db import connect_db, init_db
from web.services.lead_scoring_service import LeadScoringService


class KeywordFunnelService:
    def __init__(self, db_path, task_manager, crawl_service, im_service, scoring_service=None):
        self.db_path = db_path
        self.task_manager = task_manager
        self.crawl_service = crawl_service
        self.im_service = im_service
        self.scoring_service = scoring_service or LeadScoringService()
        with connect_db(self.db_path) as conn:
            init_db(conn)

    def queue_collect(
        self,
        keyword,
        require_num="10",
        include_comments=False,
        comment_limit="20",
        source_mode="comments_first",
        precision_mode="precision",
        risk_mode="safe",
        outreach_mode="manual",
    ):
        run_id = uuid.uuid4().hex
        require_num = int(require_num)
        comment_limit = int(comment_limit or "0")
        include_comments = bool(include_comments)
        now = self._now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "insert into keyword_runs("
                "run_id, task_id, keyword, status, require_num, include_comments, comment_limit, "
                "source_mode, precision_mode, risk_mode, outreach_mode, total_count, processed_count, lead_count, "
                "high_intent_count, contacted_count, replied_count, summary, created_at, updated_at"
                ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    "",
                    keyword,
                    "queued",
                    require_num,
                    int(include_comments),
                    comment_limit,
                    source_mode,
                    precision_mode,
                    risk_mode,
                    outreach_mode,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    "",
                    now,
                    now,
                ),
            )
            conn.commit()

        def runner():
            self._update_run(run_id, "running", 0, 0, 0, "collecting leads")
            try:
                lead_count, high_intent_count = self._collect_leads(run_id, keyword, require_num, include_comments, comment_limit)
                run = self._get_run(run_id) or {}
                total_count = int(run.get("total_count", 0))
                self._update_run(
                    run_id,
                    "success",
                    lead_count,
                    total_count,
                    total_count,
                    f"collected {lead_count} leads",
                    high_intent_count=high_intent_count,
                )
                return {"run_id": run_id, "lead_count": lead_count, "high_intent_count": high_intent_count}
            except Exception as exc:
                run = self._get_run(run_id) or {}
                self._update_run(
                    run_id,
                    "failed",
                    int(run.get("lead_count", 0)),
                    int(run.get("processed_count", 0)),
                    int(run.get("total_count", 0)),
                    f"{type(exc).__name__}: {exc}",
                    high_intent_count=int(run.get("high_intent_count", 0)),
                )
                raise

        task_id = self.task_manager.submit("keyword.collect", keyword, runner)
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update keyword_runs set task_id = ?, updated_at = ? where run_id = ?",
                (task_id, self._now(), run_id),
            )
            conn.commit()
        return {"run_id": run_id, "task_id": task_id, "keyword": keyword}

    def queue_bulk_message(self, run_id, content, limit=""):
        limit_value = int(limit) if str(limit).strip() else 0

        def runner():
            sent_count = self._send_bulk_messages(run_id, content, limit_value)
            return {"run_id": run_id, "sent_count": sent_count}

        task_id = self.task_manager.submit("keyword.bulk_message", run_id, runner)
        return {"run_id": run_id, "task_id": task_id, "content": content}

    def list_runs(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute("select * from keyword_runs order by created_at desc").fetchall()
        return [dict(row) for row in rows]

    def list_leads(self, run_id="", grade="", source_type="", review_status="", message_status=""):
        query = "select * from keyword_leads"
        clauses = []
        params = []
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if grade:
            clauses.append("grade = ?")
            params.append(grade)
        if source_type:
            clauses.append("source_type = ?")
            params.append(source_type)
        if review_status:
            clauses.append("review_status = ?")
            params.append(review_status)
        if message_status:
            clauses.append("message_status = ?")
            params.append(message_status)
        if clauses:
            query += " where " + " and ".join(clauses)
        query += " order by id desc"
        with connect_db(self.db_path) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def _collect_leads(self, run_id, keyword, require_num, include_comments, comment_limit):
        items = self.crawl_service.search_general(keyword, str(require_num), "0", "0")
        total_count = len(items)
        self._update_progress(run_id, 0, total_count, 0, f"found {total_count} works", high_intent_count=0)
        leads = []
        seen = set()
        for index, item in enumerate(items, start=1):
            author_lead = self._extract_author_lead(keyword, item)
            if author_lead and author_lead["dedupe_key"] not in seen:
                seen.add(author_lead["dedupe_key"])
                leads.append(author_lead)

            if not include_comments:
                continue

            aweme = item.get("aweme_info") or item
            aweme_id = str(aweme.get("aweme_id") or "")
            work_url = aweme.get("share_url") or self._build_work_url(aweme_id)
            if not work_url:
                continue
            comments = self.crawl_service.invoke("get_work_all_out_comment", {"work_url": work_url})
            if comment_limit > 0:
                comments = comments[:comment_limit]
            for comment in comments:
                comment_lead = self._extract_comment_lead(keyword, comment, aweme_id, work_url)
                if comment_lead and comment_lead["dedupe_key"] not in seen:
                    seen.add(comment_lead["dedupe_key"])
                    leads.append(comment_lead)
            self._update_progress(
                run_id,
                index,
                total_count,
                len(leads),
                f"processing {index}/{total_count}",
                high_intent_count=self._count_high_intent(leads),
            )
        return self._insert_leads(run_id, leads)

    def _send_bulk_messages(self, run_id, content, limit_value):
        query = "select * from keyword_leads where run_id = ? and message_status = 'pending' order by id asc"
        params = [run_id]
        if limit_value > 0:
            query += " limit ?"
            params.append(limit_value)
        with connect_db(self.db_path) as conn:
            leads = conn.execute(query, tuple(params)).fetchall()

        sent_count = 0
        for lead in leads:
            try:
                conversation = self.im_service.create_conversation(lead["user_id"])
                self.im_service.send_message(
                    conversation["conversation_id"],
                    conversation["conversation_short_id"],
                    conversation["ticket"],
                    content,
                )
                self._mark_lead_sent(lead["id"])
                sent_count += 1
            except Exception as exc:
                self._mark_lead_failed(lead["id"], f"{type(exc).__name__}: {exc}")
        return sent_count

    def _insert_leads(self, run_id, leads):
        inserted = 0
        high_intent_count = 0
        with connect_db(self.db_path) as conn:
            for lead in leads:
                cursor = conn.execute(
                    "insert into keyword_leads("
                    "run_id, keyword, source_type, source_aweme_id, source_url, user_id, sec_uid, nickname, signature, avatar_url, "
                    "comment_text, score, grade, score_reasons, matched_signals, review_status, contact_status, conversion_status, risk_flags, "
                    "raw_payload, dedupe_key, message_status, message_error, created_at, messaged_at"
                    ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    " on conflict(run_id, dedupe_key) do nothing",
                    (
                        run_id,
                        lead["keyword"],
                        lead["source_type"],
                        lead["source_aweme_id"],
                        lead["source_url"],
                        lead["user_id"],
                        lead["sec_uid"],
                        lead["nickname"],
                        lead["signature"],
                        lead["avatar_url"],
                        lead["comment_text"],
                        lead["score"],
                        lead["grade"],
                        lead["score_reasons"],
                        lead["matched_signals"],
                        lead["review_status"],
                        lead["contact_status"],
                        lead["conversion_status"],
                        lead["risk_flags"],
                        lead["raw_payload"],
                        lead["dedupe_key"],
                        lead["message_status"],
                        "",
                        self._now(),
                        None,
                    ),
                )
                inserted += cursor.rowcount
                if cursor.rowcount and lead["grade"] in {"S", "A"}:
                    high_intent_count += 1
            conn.commit()
        return inserted, high_intent_count

    def _extract_author_lead(self, keyword, item):
        aweme = item.get("aweme_info") or item
        author = aweme.get("author") or {}
        return self._build_lead(
            keyword=keyword,
            source_type="search",
            source_aweme_id=str(aweme.get("aweme_id") or ""),
            source_url=aweme.get("share_url") or self._build_work_url(aweme.get("aweme_id")),
            profile=author,
            raw_payload=item,
            content=str(aweme.get("desc") or ""),
        )

    def _extract_comment_lead(self, keyword, comment, aweme_id, source_url):
        return self._build_lead(
            keyword=keyword,
            source_type="comment",
            source_aweme_id=aweme_id,
            source_url=source_url,
            profile=comment.get("user") or {},
            raw_payload=comment,
            content=str(comment.get("text") or ""),
        )

    def _build_lead(self, keyword, source_type, source_aweme_id, source_url, profile, raw_payload, content=""):
        user_id = str(profile.get("uid") or profile.get("user_id") or "").strip()
        nickname = (profile.get("nickname") or "").strip()
        if not user_id or not nickname:
            return None
        avatar_thumb = profile.get("avatar_thumb") or {}
        avatar_list = avatar_thumb.get("url_list") or []
        comment_text = str(raw_payload.get("text") or "") if isinstance(raw_payload, dict) and source_type == "comment" else ""
        scoring = self.scoring_service.score_lead(
            {
                "source_type": source_type,
                "keyword": keyword,
                "content": content,
                "comment_text": comment_text,
                "nickname": nickname,
                "signature": str(profile.get("signature") or ""),
            }
        )
        risk_flags = scoring["risk_flags"]
        if scoring["excluded"]:
            review_status = "blocked"
            contact_status = "do_not_contact"
            message_status = "blocked"
        elif scoring["grade"] in {"S", "A"}:
            review_status = "priority"
            contact_status = "not_contacted"
            message_status = "pending"
        else:
            review_status = "new"
            contact_status = "not_contacted"
            message_status = "pending"
        return {
            "keyword": keyword,
            "source_type": source_type,
            "source_aweme_id": source_aweme_id or "",
            "source_url": source_url or "",
            "user_id": user_id,
            "sec_uid": str(profile.get("sec_uid") or ""),
            "nickname": nickname,
            "signature": str(profile.get("signature") or ""),
            "avatar_url": avatar_list[0] if avatar_list else "",
            "comment_text": comment_text,
            "score": scoring["total_score"],
            "grade": scoring["grade"],
            "score_reasons": json.dumps(scoring["reasons"], ensure_ascii=False),
            "matched_signals": json.dumps(scoring["matched_terms"], ensure_ascii=False),
            "review_status": review_status,
            "contact_status": contact_status,
            "conversion_status": "new",
            "risk_flags": json.dumps(risk_flags, ensure_ascii=False),
            "raw_payload": json.dumps(raw_payload, ensure_ascii=False),
            "dedupe_key": user_id,
            "message_status": message_status,
        }

    def _update_run(self, run_id, status, lead_count, processed_count, total_count, summary, high_intent_count=None):
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update keyword_runs set status = ?, lead_count = ?, processed_count = ?, total_count = ?, "
                "high_intent_count = ?, summary = ?, updated_at = ? where run_id = ?",
                (
                    status,
                    lead_count,
                    processed_count,
                    total_count,
                    high_intent_count if high_intent_count is not None else 0,
                    summary,
                    self._now(),
                    run_id,
                ),
            )
            conn.commit()

    def _update_progress(self, run_id, processed_count, total_count, lead_count, summary, high_intent_count=None):
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update keyword_runs set processed_count = ?, total_count = ?, lead_count = ?, high_intent_count = ?, summary = ?, updated_at = ? where run_id = ?",
                (
                    processed_count,
                    total_count,
                    lead_count,
                    high_intent_count if high_intent_count is not None else 0,
                    summary,
                    self._now(),
                    run_id,
                ),
            )
            conn.commit()

    def _mark_lead_sent(self, lead_id):
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update keyword_leads set message_status = ?, message_error = ?, contact_status = ?, messaged_at = ? where id = ?",
                ("sent", "", "contacted", self._now(), lead_id),
            )
            conn.commit()

    def _mark_lead_failed(self, lead_id, error_message):
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update keyword_leads set message_status = ?, message_error = ? where id = ?",
                ("failed", error_message, lead_id),
            )
            conn.commit()

    def _count_high_intent(self, leads):
        return sum(1 for lead in leads if lead.get("grade") in {"S", "A"})

    def _build_work_url(self, aweme_id):
        if not aweme_id:
            return ""
        return f"https://www.douyin.com/video/{aweme_id}"

    def _now(self):
        return datetime.now(UTC).isoformat()

    def _get_run(self, run_id):
        with connect_db(self.db_path) as conn:
            row = conn.execute("select * from keyword_runs where run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None
