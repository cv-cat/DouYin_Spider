from datetime import UTC, datetime, timedelta
import json
import uuid

from requests import exceptions as requests_exceptions

from web.services.crawl_service import VerificationRequiredError
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
        comment_since_hours="",
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
            self._update_run(run_id, "running", 0, 0, 0, "准备开始采集")
            try:
                lead_count, high_intent_count, comment_error_count = self._collect_leads(
                    run_id,
                    keyword,
                    require_num,
                    include_comments,
                    comment_limit,
                    comment_since_hours,
                )
                run = self._get_run(run_id) or {}
                total_count = int(run.get("total_count", 0))
                summary = f"collected {lead_count} leads"
                since_hours = self._parse_positive_int(comment_since_hours)
                if since_hours:
                    summary += f"（近 {since_hours} 小时评论精筛）"
                if comment_error_count:
                    summary += f"，跳过 {comment_error_count} 条作品评论抓取失败"
                self._update_run(
                    run_id,
                    "success",
                    lead_count,
                    total_count,
                    total_count,
                    summary,
                    high_intent_count=high_intent_count,
                )
                return {
                    "run_id": run_id,
                    "lead_count": lead_count,
                    "high_intent_count": high_intent_count,
                    "comment_error_count": comment_error_count,
                }
            except VerificationRequiredError as exc:
                run = self._get_run(run_id) or {}
                self._update_run(
                    run_id,
                    "verification_required",
                    int(run.get("lead_count", 0)),
                    int(run.get("processed_count", 0)),
                    int(run.get("total_count", 0)),
                    str(exc),
                    high_intent_count=int(run.get("high_intent_count", 0)),
                )
                raise
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

    def clear_leads(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute("select id from keyword_leads").fetchall()
            lead_ids = [row["id"] for row in rows]
            if lead_ids:
                placeholders = ",".join("?" for _ in lead_ids)
                conn.execute(f"delete from outreach_events where lead_id in ({placeholders})", tuple(lead_ids))
            conn.execute("delete from keyword_leads")
            conn.execute(
                "update keyword_runs set lead_count = 0, high_intent_count = 0, contacted_count = 0, replied_count = 0"
            )
            conn.commit()
        return len(lead_ids)

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
        return [self._decorate_run(dict(row)) for row in rows]

    def list_leads(
        self,
        run_id="",
        grade="",
        source_type="",
        review_status="",
        message_status="",
        created_from="",
        created_to="",
        intent_query="",
    ):
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
        normalized_from = self._normalize_created_bound(created_from, upper=False)
        if normalized_from:
            clauses.append("created_at >= ?")
            params.append(normalized_from)
        normalized_to = self._normalize_created_bound(created_to, upper=True)
        if normalized_to:
            clauses.append("created_at <= ?")
            params.append(normalized_to)
        if intent_query:
            clauses.append(
                "("
                "lower(comment_text) like ? or "
                "lower(matched_signals) like ? or "
                "lower(score_reasons) like ?"
                ")"
            )
            like_value = f"%{str(intent_query).strip().lower()}%"
            params.extend([like_value, like_value, like_value])
        if clauses:
            query += " where " + " and ".join(clauses)
        query += " order by id desc"
        with connect_db(self.db_path) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decorate_lead(dict(row)) for row in rows]

    def send_lead_message(self, lead_id, content, template_key="", mode="manual"):
        with connect_db(self.db_path) as conn:
            row = conn.execute("select * from keyword_leads where id = ?", (int(lead_id),)).fetchone()
        if not row:
            raise RuntimeError("Lead not found")
        lead = dict(row)
        if lead.get("message_status") == "blocked" or lead.get("contact_status") == "do_not_contact":
            raise RuntimeError("Lead is blocked for outreach")

        note = content
        status = "sent"
        try:
            conversation = self.im_service.create_conversation(lead["user_id"])
            self.im_service.send_message(
                conversation["conversation_id"],
                conversation["conversation_short_id"],
                conversation["ticket"],
                content,
            )
            self._mark_lead_sent(lead["id"])
        except Exception as exc:
            status = "failed"
            note = f"{type(exc).__name__}: {exc}"
            self._mark_lead_failed(lead["id"], note)
            self._record_outreach_event(lead["id"], mode, template_key, status, note)
            raise

        self._record_outreach_event(lead["id"], mode, template_key, status, note)
        return {"lead_id": lead["id"], "nickname": lead["nickname"], "status": status}

    def rescore_existing_leads(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute("select * from keyword_leads order by id asc").fetchall()
            run_ids = set()
            for row in rows:
                lead = dict(row)
                raw_payload = self._safe_load_json(lead.get("raw_payload"))
                scoring_state = self._score_lead_state(
                    lead.get("keyword"),
                    lead.get("source_type"),
                    self._extract_source_content(lead.get("source_type"), lead.get("comment_text"), raw_payload),
                    lead.get("comment_text"),
                    lead.get("nickname"),
                    lead.get("signature"),
                )
                review_status = scoring_state["review_status"]
                contact_status = lead.get("contact_status") or "not_contacted"
                message_status = lead.get("message_status") or "pending"
                if review_status == "blocked":
                    if contact_status != "contacted":
                        contact_status = "do_not_contact"
                    if message_status not in {"sent", "failed"}:
                        message_status = "blocked"
                else:
                    if contact_status == "do_not_contact":
                        contact_status = "not_contacted"
                    if message_status not in {"sent", "failed"}:
                        message_status = "pending"
                conn.execute(
                    "update keyword_leads set score = ?, grade = ?, score_reasons = ?, matched_signals = ?, "
                    "review_status = ?, contact_status = ?, risk_flags = ?, message_status = ? where id = ?",
                    (
                        scoring_state["score"],
                        scoring_state["grade"],
                        scoring_state["score_reasons"],
                        scoring_state["matched_signals"],
                        review_status,
                        contact_status,
                        scoring_state["risk_flags"],
                        message_status,
                        lead["id"],
                    ),
                )
                run_ids.add(str(lead.get("run_id") or ""))
            now = self._now()
            for run_id in filter(None, run_ids):
                counts = conn.execute(
                    "select count(*) as lead_count, "
                    "sum(case when grade in ('S', 'A') then 1 else 0 end) as high_intent_count "
                    "from keyword_leads where run_id = ?",
                    (run_id,),
                ).fetchone()
                conn.execute(
                    "update keyword_runs set lead_count = ?, high_intent_count = ?, updated_at = ? where run_id = ?",
                    (
                        int(counts["lead_count"] or 0),
                        int(counts["high_intent_count"] or 0),
                        now,
                        run_id,
                    ),
                )
            conn.commit()

    def _decorate_lead(self, lead):
        sec_uid = str(lead.get("sec_uid") or "").strip()
        lead["profile_url"] = f"https://www.douyin.com/user/{sec_uid}" if sec_uid else ""
        lead["source_label"] = {
            "comment": "评论区",
            "search": "搜索作者",
            "live": "直播间",
        }.get(str(lead.get("source_type") or ""), str(lead.get("source_type") or "-"))
        lead["review_status_label"] = {
            "priority": "高意向",
            "new": "待筛选",
            "blocked": "已屏蔽",
        }.get(str(lead.get("review_status") or ""), str(lead.get("review_status") or "-"))
        lead["message_status_label"] = {
            "pending": "待触达",
            "sent": "已发送",
            "failed": "发送失败",
            "blocked": "禁止触达",
        }.get(str(lead.get("message_status") or ""), str(lead.get("message_status") or "-"))
        lead["contact_status_label"] = {
            "not_contacted": "未联系",
            "contacted": "已联系",
            "do_not_contact": "勿扰",
        }.get(str(lead.get("contact_status") or ""), str(lead.get("contact_status") or "-"))
        lead["conversion_status_label"] = {
            "new": "未转化",
            "replied": "已回复",
            "contact_added": "已加联系方式",
            "paid": "已成交",
        }.get(str(lead.get("conversion_status") or ""), str(lead.get("conversion_status") or "-"))
        lead["matched_signal_list"] = self._parse_json_list(lead.get("matched_signals"))
        lead["score_reason_list"] = self._parse_json_list(lead.get("score_reasons"))
        lead["risk_flag_list"] = self._parse_json_list(lead.get("risk_flags"))
        lead["profile_metrics"] = self._extract_profile_metrics(lead)
        lead["comment_created_at_label"] = self._extract_comment_created_at_label(lead)
        return lead

    def _parse_json_list(self, raw_value):
        if not raw_value:
            return []
        if isinstance(raw_value, list):
            return [str(item) for item in raw_value if str(item).strip()]
        try:
            payload = json.loads(raw_value)
        except Exception:
            return [str(raw_value)]
        if not isinstance(payload, list):
            return [str(raw_value)]
        return [str(item) for item in payload if str(item).strip()]

    def _extract_comment_created_at_label(self, lead):
        if str(lead.get("source_type") or "") != "comment":
            return ""
        raw_payload = str(lead.get("raw_payload") or "").strip()
        if not raw_payload:
            return ""
        try:
            payload = json.loads(raw_payload)
        except Exception:
            return ""
        create_time = payload.get("create_time")
        if not create_time:
            return ""
        try:
            timestamp = int(create_time)
        except (TypeError, ValueError):
            return ""
        return datetime.fromtimestamp(timestamp, UTC).astimezone().strftime("%Y-%m-%d %H:%M")

    def _normalize_created_bound(self, value, upper=False):
        text = str(value or "").strip()
        if not text:
            return ""
        if len(text) == 10 and text.count("-") == 2:
            return f"{text}T23:59:59.999999+00:00" if upper else f"{text}T00:00:00+00:00"
        return text

    def _collect_leads(self, run_id, keyword, require_num, include_comments, comment_limit, comment_since_hours=""):
        items = self.crawl_service.search_general(keyword, str(require_num), "0", "0")
        run = self._get_run(run_id) or {}
        precision_mode = str(run.get("precision_mode") or "precision")
        source_mode = str(run.get("source_mode") or "comments_first")
        since_hours = self._parse_positive_int(comment_since_hours)
        comment_cutoff = datetime.now(UTC) - timedelta(hours=since_hours) if since_hours else None
        total_count = len(items)
        summary = f"已找到 {total_count} 条作品，准备开始处理"
        if source_mode == "comments_only":
            summary += "，只保留评论区线索"
        if since_hours:
            summary += f"，只保留近 {since_hours} 小时评论"
        self._update_progress(run_id, 0, total_count, 0, summary, high_intent_count=0)
        seen = set()
        inserted_total = 0
        high_intent_total = 0
        comment_error_count = 0
        for index, item in enumerate(items, start=1):
            if source_mode != "comments_only":
                self._update_progress(
                    run_id,
                    index - 1,
                    total_count,
                    inserted_total,
                    f"正在处理第 {index}/{total_count} 条作品：提取作者",
                    high_intent_count=high_intent_total,
                )
                author_lead = self._extract_author_lead(keyword, item)
                if author_lead and self._should_include_lead(author_lead, precision_mode) and author_lead["dedupe_key"] not in seen:
                    author_lead = self._enrich_lead_profile(author_lead)
                    seen.add(author_lead["dedupe_key"])
                    inserted_count, high_intent_count = self._insert_leads(run_id, [author_lead])
                    inserted_total += inserted_count
                    high_intent_total += high_intent_count
                    self._update_progress(
                        run_id,
                        index - 1,
                        total_count,
                        inserted_total,
                        f"正在处理第 {index}/{total_count} 条作品：已新增 {inserted_total} 条线索，准备抓取评论",
                        high_intent_count=high_intent_total,
                    )

            if not include_comments:
                self._update_progress(
                    run_id,
                    index,
                    total_count,
                    inserted_total,
                    f"已完成 {index}/{total_count} 条作品，累计 {inserted_total} 条线索",
                    high_intent_count=high_intent_total,
                )
                continue

            aweme = item.get("aweme_info") or item
            aweme_id = str(aweme.get("aweme_id") or "")
            work_url = aweme.get("share_url") or self._build_work_url(aweme_id)
            if not work_url:
                self._update_progress(
                    run_id,
                    index,
                    total_count,
                    inserted_total,
                    f"第 {index}/{total_count} 条作品缺少地址，已跳过",
                    high_intent_count=high_intent_total,
                )
                continue
            self._update_progress(
                run_id,
                index - 1,
                total_count,
                inserted_total,
                f"正在处理第 {index}/{total_count} 条作品：抓取评论",
                high_intent_count=high_intent_total,
            )
            try:
                comments = self._fetch_comments(work_url, comment_limit)
            except (requests_exceptions.RequestException, json.JSONDecodeError) as exc:
                comment_error_count += 1
                self._update_progress(
                    run_id,
                    index,
                    total_count,
                    inserted_total,
                    f"第 {index}/{total_count} 条作品评论抓取失败，已跳过：{type(exc).__name__}: {exc}",
                    high_intent_count=high_intent_total,
                )
                continue
            if comment_cutoff:
                comments = [comment for comment in comments if self._comment_is_recent(comment, comment_cutoff)]
            item_comment_leads = []
            for comment in comments:
                comment_lead = self._extract_comment_lead(keyword, comment, aweme_id, work_url)
                if comment_lead and self._should_include_lead(comment_lead, precision_mode) and comment_lead["dedupe_key"] not in seen:
                    comment_lead = self._enrich_lead_profile(comment_lead)
                    seen.add(comment_lead["dedupe_key"])
                    item_comment_leads.append(comment_lead)
            if item_comment_leads:
                inserted_count, high_intent_count = self._insert_leads(run_id, item_comment_leads)
                inserted_total += inserted_count
                high_intent_total += high_intent_count
            self._update_progress(
                run_id,
                index,
                total_count,
                inserted_total,
                f"已完成 {index}/{total_count} 条作品，累计 {inserted_total} 条线索",
                high_intent_count=high_intent_total,
            )
        return inserted_total, high_intent_total, comment_error_count

    def _parse_positive_int(self, value):
        try:
            parsed = int(str(value or "").strip())
        except (TypeError, ValueError):
            return 0
        return parsed if parsed > 0 else 0

    def _comment_is_recent(self, comment, cutoff):
        try:
            create_time = int(comment.get("create_time"))
        except (TypeError, ValueError):
            return False
        return datetime.fromtimestamp(create_time, UTC) >= cutoff

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
                    "profile_json, raw_payload, dedupe_key, message_status, message_error, created_at, messaged_at"
                    ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
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
                        lead["profile_json"],
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
        scoring_state = self._score_lead_state(
            keyword,
            source_type,
            content,
            comment_text,
            nickname,
            str(profile.get("signature") or ""),
        )
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
            "score": scoring_state["score"],
            "grade": scoring_state["grade"],
            "score_reasons": scoring_state["score_reasons"],
            "matched_signals": scoring_state["matched_signals"],
            "review_status": scoring_state["review_status"],
            "contact_status": scoring_state["contact_status"],
            "conversion_status": "new",
            "risk_flags": scoring_state["risk_flags"],
            "profile_json": "{}",
            "raw_payload": json.dumps(raw_payload, ensure_ascii=False),
            "dedupe_key": user_id,
            "message_status": scoring_state["message_status"],
        }

    def _score_lead_state(self, keyword, source_type, content, comment_text, nickname, signature):
        scoring = self.scoring_service.score_lead(
            {
                "source_type": source_type,
                "keyword": keyword,
                "content": content,
                "comment_text": comment_text,
                "nickname": nickname,
                "signature": signature,
            }
        )
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
            "score": scoring["total_score"],
            "grade": scoring["grade"],
            "score_reasons": json.dumps(scoring["reasons"], ensure_ascii=False),
            "matched_signals": json.dumps(scoring["matched_terms"], ensure_ascii=False),
            "risk_flags": json.dumps(scoring["risk_flags"], ensure_ascii=False),
            "review_status": review_status,
            "contact_status": contact_status,
            "message_status": message_status,
        }

    def _should_include_lead(self, lead, precision_mode):
        if lead["message_status"] == "blocked":
            return False
        allowed_grades = {
            "precision": {"S", "A"},
            "balanced": {"S", "A", "B"},
            "wide": {"S", "A", "B", "C"},
        }
        return lead["grade"] in allowed_grades.get(precision_mode, allowed_grades["precision"])

    def _enrich_lead_profile(self, lead):
        sec_uid = str(lead.get("sec_uid") or "").strip()
        if not sec_uid or not hasattr(self.crawl_service, "lookup_user"):
            return lead
        user_url = f"https://www.douyin.com/user/{sec_uid}"
        try:
            payload = self.crawl_service.lookup_user(user_url) or {}
        except Exception:
            return lead
        user = payload.get("user") or {}
        avatar_thumb = user.get("avatar_thumb") or {}
        avatar_list = avatar_thumb.get("url_list") or []
        lead["nickname"] = str(user.get("nickname") or lead["nickname"])
        lead["signature"] = str(user.get("signature") or lead["signature"])
        lead["avatar_url"] = avatar_list[0] if avatar_list else lead["avatar_url"]
        lead["profile_json"] = json.dumps(payload, ensure_ascii=False)
        return lead

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

    def _record_outreach_event(self, lead_id, mode, template_key, status, note):
        with connect_db(self.db_path) as conn:
            conn.execute(
                "insert into outreach_events(lead_id, mode, template_key, status, note, created_at) values(?, ?, ?, ?, ?, ?)",
                (lead_id, mode, template_key, status, note, self._now()),
            )
            conn.commit()

    def _fetch_comments(self, work_url, comment_limit):
        limit_value = int(comment_limit or 0)
        if limit_value <= 0:
            return []
        cursor = "0"
        comments = []
        while len(comments) < limit_value:
            payload = self.crawl_service.invoke("get_work_out_comment", {"work_url": work_url, "cursor": cursor})
            page_comments = payload.get("comments") or []
            if not page_comments:
                break
            remaining = limit_value - len(comments)
            comments.extend(page_comments[:remaining])
            if len(comments) >= limit_value or payload.get("has_more") != 1:
                break
            next_cursor = str(payload.get("cursor") or "")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return comments

    def _build_work_url(self, aweme_id):
        if not aweme_id:
            return ""
        return f"https://www.douyin.com/video/{aweme_id}"

    def _extract_source_content(self, source_type, comment_text, raw_payload):
        if source_type == "comment":
            return str(comment_text or "")
        if isinstance(raw_payload, dict):
            aweme = raw_payload.get("aweme_info") or raw_payload
            return str(aweme.get("desc") or "")
        return ""

    def _extract_profile_metrics(self, lead):
        payload = self._safe_load_json(lead.get("profile_json"))
        user = payload.get("user") or payload
        metric_map = [
            ("关注", user.get("following_count")),
            ("粉丝", user.get("follower_count")),
            ("作品", user.get("aweme_count")),
            ("获赞", user.get("total_favorited")),
        ]
        metrics = []
        for label, value in metric_map:
            if value in (None, "", "null"):
                continue
            metrics.append({"label": label, "value": str(value)})
        return metrics

    def _safe_load_json(self, raw_value):
        if isinstance(raw_value, dict):
            return raw_value
        text = str(raw_value or "").strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _now(self):
        return datetime.now(UTC).isoformat()

    def _get_run(self, run_id):
        with connect_db(self.db_path) as conn:
            row = conn.execute("select * from keyword_runs where run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def _decorate_run(self, run):
        run["status_label"] = self._status_label(run)
        run["strategy_summary"] = " / ".join(
            [
                self._mode_label("source", run.get("source_mode")),
                self._mode_label("precision", run.get("precision_mode")),
                self._mode_label("risk", run.get("risk_mode")),
                self._mode_label("outreach", run.get("outreach_mode")),
            ]
        )
        missing_requirement, next_step = self._run_guidance(run)
        run["missing_requirement"] = missing_requirement
        run["next_step"] = next_step
        return run

    def _status_label(self, run):
        mapping = {
            "queued": "排队中",
            "running": "运行中",
            "success": "已完成",
            "failed": "已失败",
            "verification_required": "需要人工验证",
        }
        return mapping.get(run.get("status"), str(run.get("status") or "unknown"))

    def _mode_label(self, group, key):
        labels = {
            "source": {
                "comments_first": "评论区优先",
                "comments_only": "只看评论区",
                "search_first": "搜索优先",
                "live_first": "直播补充",
            },
            "precision": {
                "precision": "少而准",
                "balanced": "平衡",
                "wide": "多而广",
            },
            "risk": {
                "safe": "安全优先",
                "balanced": "平衡",
                "aggressive": "激进",
            },
            "outreach": {
                "manual": "人工审核",
                "semi_auto": "半自动触达",
                "batch": "批量私信",
            },
        }
        return labels.get(group, {}).get(key, str(key or "-"))

    def _run_guidance(self, run):
        status = str(run.get("status") or "")
        summary = str(run.get("summary") or "")
        summary_lower = summary.lower()
        if status == "verification_required" or "verify" in summary_lower:
            return "缺少抖音人工验证", "先在浏览器完成验证，再重新发起任务"
        if "missing douyin cookie" in summary_lower:
            return "缺少 douyin 登录态", "先到登录中心保存 douyin Cookie"
        if "missing live cookie" in summary_lower:
            return "缺少 live 登录态", "先到登录中心保存 live Cookie"
        if any(keyword in summary_lower for keyword in ("sslerror", "proxyerror", "readtimeout", "connectionerror", "requestexception")):
            return "评论抓取连接异常", "可直接重试，或关闭评论抓取后继续"
        if status == "success" and int(run.get("lead_count", 0)) == 0:
            return "当前没有符合条件的线索", "换关键词，或把精度调成平衡/多而广后重试"
        if status == "success" and int(run.get("high_intent_count", 0)) == 0:
            return "高意向线索不足", "优先换更强意图关键词，或切到评论区优先"
        if status == "running":
            return "当前无需补资料", "先等待当前步骤完成；若长时间不动，再按页面提示处理"
        if status == "queued":
            return "等待后台线程开始执行", "先等待 1-2 秒自动刷新"
        if status == "failed":
            return "需要根据错误处理", "展开摘要或错误面板，按报错继续处理"
        return "-", "-"
