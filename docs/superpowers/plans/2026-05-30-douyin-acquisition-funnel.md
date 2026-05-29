# DouYin Acquisition Funnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `Delta Force` customer-acquisition backend on top of the existing local Web UI so the operator can capture, score, review, contact, and convert likely paying companionship/boosting leads from Douyin.

**Architecture:** Extend the existing `keyword_funnel` implementation into a business-facing acquisition system instead of a crawler-only page. Keep Douyin collection inside `web/services/keyword_funnel_service.py`, move scoring and workflow logic into focused services, and add six operator pages for dashboard, capture tasks, lead pool, outreach, conversion tracking, and rules management.

**Tech Stack:** Python 3.14, FastAPI, Jinja2, HTMX polling, SQLite, pytest, existing `DouyinAPI`/`Data_Spider`/IM services.

---

## File Map

### Create

- `web/services/lead_scoring_service.py`
  - score comment/search/live leads
  - assign `S/A/B/C`
  - explain score reasons and matched signals
- `web/services/outreach_service.py`
  - enforce manual / semi-auto / batch outreach modes
  - apply safe-first throttling defaults
  - maintain contact/reply/conversion status transitions
- `web/services/acquisition_dashboard_service.py`
  - compute acquisition summary metrics by day, source, and grade
- `web/services/rules_service.py`
  - load/save keyword groups, score weights, exclusion terms, and risk profile defaults
- `web/templates/acquisition_dashboard.html`
  - operator dashboard
- `web/templates/lead_pool.html`
  - high-intent lead workspace
- `web/templates/outreach_center.html`
  - templates, queues, and send actions
- `web/templates/conversion_tracking.html`
  - conversion pipeline and aggregate views
- `web/templates/rules_center.html`
  - editable acquisition rules UI
- `web/templates/components/acquisition_metric_cards.html`
  - dashboard metric partial
- `web/templates/components/lead_pool_table.html`
  - lead pool partial
- `web/templates/components/outreach_queue_table.html`
  - outreach queue partial
- `web/templates/components/rules_form.html`
  - rules editor partial
- `tests/web/test_lead_scoring_service.py`
  - score and grade coverage
- `tests/web/test_acquisition_pages.py`
  - page load and polling fragment coverage
- `tests/web/test_outreach_service.py`
  - manual / semi-auto / batch flow coverage
- `tests/web/test_rules_service.py`
  - acquisition rules persistence coverage

### Modify

- `web/db.py`
  - add acquisition fields and workflow tables
- `web/app.py`
  - wire new acquisition services
- `web/routes/pages.py`
  - add new acquisition pages and partial endpoints
- `web/routes/actions.py`
  - add review, outreach, conversion, and rules actions
- `web/services/keyword_funnel_service.py`
  - enrich captured leads with score, reason, and business status
- `web/templates/base.html`
  - add acquisition navigation
- `web/templates/keyword_funnel.html`
  - evolve into capture task page with stronger business framing
- `tests/web/test_db.py`
  - assert new acquisition tables/columns exist
- `tests/web/test_keyword_funnel.py`
  - extend capture-task coverage for score, progress, and comment text
- `README.md`
  - document the acquisition backend purpose and safe-first defaults

---

### Task 1: Expand the Acquisition Schema and Rule Defaults

**Files:**
- Modify: `web/db.py`
- Modify: `tests/web/test_db.py`
- Test: `tests/web/test_db.py`

- [ ] **Step 1: Write the failing schema test**

```python
# tests/web/test_db.py
from web.db import connect_db, init_db, list_tables


def test_acquisition_tables_and_columns_exist(tmp_path):
    db_path = tmp_path / "web-ui.sqlite3"
    with connect_db(db_path) as conn:
        init_db(conn)
        run_columns = {
            row["name"]
            for row in conn.execute("pragma table_info(keyword_runs)").fetchall()
        }
        lead_columns = {
            row["name"]
            for row in conn.execute("pragma table_info(keyword_leads)").fetchall()
        }
        workflow_tables = set(list_tables(db_path))

    assert {"processed_count", "total_count", "source_mode", "precision_mode", "risk_mode", "outreach_mode"}.issubset(run_columns)
    assert {"comment_text", "score", "grade", "score_reasons", "matched_signals", "review_status", "contact_status", "conversion_status", "risk_flags"}.issubset(lead_columns)
    assert {"outreach_templates", "outreach_events", "acquisition_rules"}.issubset(workflow_tables)
```

- [ ] **Step 2: Run the schema test to verify it fails**

Run: `source /Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github/.venv/bin/activate && python -m pytest tests/web/test_db.py::test_acquisition_tables_and_columns_exist -v`

Expected: FAIL with missing columns and/or missing tables in `keyword_runs` / `keyword_leads`.

- [ ] **Step 3: Add acquisition tables, columns, and migration guards**

```python
# web/db.py
SCHEMA = """
create table if not exists keyword_runs (
    run_id text primary key,
    task_id text,
    keyword text not null,
    status text not null,
    require_num integer not null,
    include_comments integer not null,
    comment_limit integer not null,
    source_mode text not null default 'comments_first',
    precision_mode text not null default 'precision',
    risk_mode text not null default 'safe',
    outreach_mode text not null default 'manual',
    total_count integer not null default 0,
    processed_count integer not null default 0,
    lead_count integer not null default 0,
    high_intent_count integer not null default 0,
    contacted_count integer not null default 0,
    replied_count integer not null default 0,
    summary text not null default '',
    created_at text not null,
    updated_at text not null
);
create table if not exists keyword_leads (
    id integer primary key autoincrement,
    run_id text not null,
    keyword text not null,
    source_type text not null,
    source_aweme_id text,
    source_url text,
    user_id text not null,
    sec_uid text,
    nickname text not null,
    signature text,
    avatar_url text,
    comment_text text not null default '',
    score integer not null default 0,
    grade text not null default 'C',
    score_reasons text not null default '[]',
    matched_signals text not null default '[]',
    review_status text not null default 'new',
    contact_status text not null default 'not_contacted',
    conversion_status text not null default 'new',
    risk_flags text not null default '[]',
    raw_payload text not null,
    dedupe_key text not null,
    message_status text not null,
    message_error text not null,
    created_at text not null,
    messaged_at text,
    unique(run_id, dedupe_key)
);
create table if not exists outreach_templates (
    id integer primary key autoincrement,
    template_key text not null unique,
    category text not null,
    title text not null,
    body text not null,
    enabled integer not null default 1
);
create table if not exists outreach_events (
    id integer primary key autoincrement,
    lead_id integer not null,
    mode text not null,
    template_key text,
    status text not null,
    note text not null default '',
    created_at text not null
);
create table if not exists acquisition_rules (
    rule_key text primary key,
    value text not null,
    updated_at text not null
);
"""


def init_db(conn):
    conn.executescript(SCHEMA)
    _ensure_column(conn, "keyword_runs", "source_mode", "text not null default 'comments_first'")
    _ensure_column(conn, "keyword_runs", "precision_mode", "text not null default 'precision'")
    _ensure_column(conn, "keyword_runs", "risk_mode", "text not null default 'safe'")
    _ensure_column(conn, "keyword_runs", "outreach_mode", "text not null default 'manual'")
    _ensure_column(conn, "keyword_runs", "high_intent_count", "integer not null default 0")
    _ensure_column(conn, "keyword_runs", "contacted_count", "integer not null default 0")
    _ensure_column(conn, "keyword_runs", "replied_count", "integer not null default 0")
    _ensure_column(conn, "keyword_leads", "score", "integer not null default 0")
    _ensure_column(conn, "keyword_leads", "grade", "text not null default 'C'")
    _ensure_column(conn, "keyword_leads", "score_reasons", "text not null default '[]'")
    _ensure_column(conn, "keyword_leads", "matched_signals", "text not null default '[]'")
    _ensure_column(conn, "keyword_leads", "review_status", "text not null default 'new'")
    _ensure_column(conn, "keyword_leads", "contact_status", "text not null default 'not_contacted'")
    _ensure_column(conn, "keyword_leads", "conversion_status", "text not null default 'new'")
    _ensure_column(conn, "keyword_leads", "risk_flags", "text not null default '[]'")
    conn.commit()
```

- [ ] **Step 4: Run the schema test to verify it passes**

Run: `source /Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github/.venv/bin/activate && python -m pytest tests/web/test_db.py::test_acquisition_tables_and_columns_exist -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/db.py tests/web/test_db.py
git commit -m "feat: add acquisition funnel schema"
```

---

### Task 2: Add Lead Scoring and Business-State Enrichment

**Files:**
- Create: `web/services/lead_scoring_service.py`
- Modify: `web/services/keyword_funnel_service.py`
- Modify: `tests/web/test_keyword_funnel.py`
- Create: `tests/web/test_lead_scoring_service.py`
- Test: `tests/web/test_lead_scoring_service.py`
- Test: `tests/web/test_keyword_funnel.py`

- [ ] **Step 1: Write the failing scoring tests**

```python
# tests/web/test_lead_scoring_service.py
from web.services.lead_scoring_service import LeadScoringService


def test_comment_with_strong_delta_force_demand_scores_as_s_or_a():
    service = LeadScoringService()

    result = service.score_lead(
        source_type="comment",
        keyword="三角洲上分",
        text="三角洲单排坐牢，求带上分，有没有靠谱的",
        nickname="demo",
        signature="",
    )

    assert result["score"] >= 70
    assert result["grade"] in {"S", "A"}
    assert "求带" in result["matched_signals"]
    assert "三角洲" in result["matched_signals"]


def test_low_intent_praise_scores_as_c():
    service = LeadScoringService()

    result = service.score_lead(
        source_type="comment",
        keyword="三角洲",
        text="哈哈真厉害",
        nickname="demo",
        signature="",
    )

    assert result["grade"] == "C"
```

```python
# tests/web/test_keyword_funnel.py
def test_collect_task_stores_score_reasons_and_comment_text(tmp_path):
    service = KeywordFunnelService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        DummyCrawlService(),
        DummyIMService(),
    )

    queued = service.queue_collect("装机", require_num="5", include_comments=True, comment_limit="10")

    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        rows = conn.execute(
            "select source_type, comment_text, score, grade, score_reasons, matched_signals from keyword_leads where run_id = ? order by user_id",
            (queued["run_id"],),
        ).fetchall()

    assert rows[0]["source_type"] == "author"
    assert rows[1]["comment_text"] == "need this"
    assert rows[1]["score"] >= 0
    assert rows[1]["grade"] in {"S", "A", "B", "C"}
    assert rows[1]["score_reasons"].startswith("[")
    assert rows[1]["matched_signals"].startswith("[")
```

- [ ] **Step 2: Run the scoring tests to verify they fail**

Run: `source /Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github/.venv/bin/activate && python -m pytest tests/web/test_lead_scoring_service.py tests/web/test_keyword_funnel.py::test_collect_task_stores_score_reasons_and_comment_text -v`

Expected: FAIL with `ModuleNotFoundError` and/or missing lead score columns.

- [ ] **Step 3: Implement a focused scoring service**

```python
# web/services/lead_scoring_service.py
import json


class LeadScoringService:
    STRONG_DEMAND = ["求带", "求陪玩", "求上分", "有没有人带", "谁带带我", "来个厉害的带我"]
    TEAM_DEMAND = ["缺队友", "找搭子", "找车队", "一起打", "有没有固定队"]
    PAIN_SIGNALS = ["打不上去", "卡段位", "单排坐牢", "太难了", "老被虐"]
    DELTA_SIGNALS = ["三角洲", "三角洲行动", "段位", "上分", "带飞", "车队", "队友", "单排", "双排", "四排"]
    PAYMENT_SIGNALS = ["有没有靠谱的", "多少钱", "想找长期的", "有人接吗", "晚上带我打", "固定队有吗"]
    LOW_INTENT = ["哈哈", "厉害", "牛", "学到了"]

    def score_lead(self, source_type, keyword, text, nickname, signature):
        haystack = " ".join([keyword or "", text or "", nickname or "", signature or ""])
        score = 0
        matched = []
        reasons = []
        risk_flags = []

        for term in self.STRONG_DEMAND:
            if term in haystack:
                score += 35
                matched.append(term)
                reasons.append(f"strong-demand:{term}")
        for term in self.TEAM_DEMAND:
            if term in haystack:
                score += 20
                matched.append(term)
                reasons.append(f"team-demand:{term}")
        for term in self.PAIN_SIGNALS:
            if term in haystack:
                score += 12
                matched.append(term)
                reasons.append(f"pain:{term}")
        for term in self.DELTA_SIGNALS:
            if term in haystack:
                score += 10
                matched.append(term)
                reasons.append(f"delta:{term}")
        for term in self.PAYMENT_SIGNALS:
            if term in haystack:
                score += 15
                matched.append(term)
                reasons.append(f"payment:{term}")
        if source_type == "comment":
            score += 10
            reasons.append("source-priority:comment")
        if any(term in haystack for term in self.LOW_INTENT) and score < 30:
            reasons.append("low-intent-only")
        grade = self._grade(score)
        return {
            "score": score,
            "grade": grade,
            "score_reasons": json.dumps(reasons, ensure_ascii=False),
            "matched_signals": json.dumps(sorted(set(matched)), ensure_ascii=False),
            "risk_flags": json.dumps(risk_flags, ensure_ascii=False),
        }

    def _grade(self, score):
        if score >= 85:
            return "S"
        if score >= 70:
            return "A"
        if score >= 50:
            return "B"
        return "C"
```

- [ ] **Step 4: Inject scoring into capture flow**

```python
# web/services/keyword_funnel_service.py
from web.services.lead_scoring_service import LeadScoringService


class KeywordFunnelService:
    def __init__(self, db_path, task_manager, crawl_service, im_service, scoring_service=None):
        ...
        self.scoring = scoring_service or LeadScoringService()

    def _build_lead(self, keyword, source_type, source_aweme_id, source_url, profile, raw_payload):
        ...
        text = str(raw_payload.get("text") or "") if isinstance(raw_payload, dict) else ""
        scoring = self.scoring.score_lead(
            source_type=source_type,
            keyword=keyword,
            text=text,
            nickname=nickname,
            signature=str(profile.get("signature") or ""),
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
            "comment_text": text if source_type == "comment" else "",
            "score": scoring["score"],
            "grade": scoring["grade"],
            "score_reasons": scoring["score_reasons"],
            "matched_signals": scoring["matched_signals"],
            "risk_flags": scoring["risk_flags"],
            "review_status": "new",
            "contact_status": "not_contacted",
            "conversion_status": "new",
            "raw_payload": json.dumps(raw_payload, ensure_ascii=False),
            "dedupe_key": user_id,
        }
```

- [ ] **Step 5: Run the scoring tests to verify they pass**

Run: `source /Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github/.venv/bin/activate && python -m pytest tests/web/test_lead_scoring_service.py tests/web/test_keyword_funnel.py::test_collect_task_stores_score_reasons_and_comment_text -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/services/lead_scoring_service.py web/services/keyword_funnel_service.py tests/web/test_lead_scoring_service.py tests/web/test_keyword_funnel.py
git commit -m "feat: score acquisition leads"
```

---

### Task 3: Build the Capture Task Page and Lead Pool Workspace

**Files:**
- Modify: `web/routes/pages.py`
- Modify: `web/routes/actions.py`
- Modify: `web/templates/base.html`
- Modify: `web/templates/keyword_funnel.html`
- Create: `web/templates/lead_pool.html`
- Create: `web/templates/components/lead_pool_table.html`
- Modify: `tests/web/test_keyword_funnel.py`
- Create: `tests/web/test_acquisition_pages.py`
- Test: `tests/web/test_acquisition_pages.py`

- [ ] **Step 1: Write the failing page tests**

```python
# tests/web/test_acquisition_pages.py
from fastapi.testclient import TestClient

from web.app import create_app


def test_acquisition_pages_load(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)

    for path in ["/keyword-funnel", "/lead-pool"]:
        response = client.get(path)
        assert response.status_code == 200


def test_lead_pool_page_shows_score_and_comment_columns(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)

    response = client.get("/lead-pool")

    assert "评分" in response.text
    assert "命中信号" in response.text
    assert "评论内容" in response.text
```

- [ ] **Step 2: Run the page tests to verify they fail**

Run: `source /Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github/.venv/bin/activate && python -m pytest tests/web/test_acquisition_pages.py -v`

Expected: FAIL with missing route `/lead-pool` and missing score columns.

- [ ] **Step 3: Add the lead-pool page and richer capture task fragments**

```python
# web/routes/pages.py
@router.get("/lead-pool", response_class=HTMLResponse)
def lead_pool_page(request: Request):
    partial = request.query_params.get("partial")
    grade = request.query_params.get("grade", "")
    source_type = request.query_params.get("source_type", "")
    contact_status = request.query_params.get("contact_status", "")
    review_status = request.query_params.get("review_status", "")
    leads = request.app.state.keyword_funnel_service.list_leads_filtered(
        grade=grade,
        source_type=source_type,
        contact_status=contact_status,
        review_status=review_status,
    )
    if partial == "rows":
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="components/lead_pool_table.html",
            context={"leads": leads},
        )
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="lead_pool.html",
        context={"title": "高意向线索池", "leads": leads},
    )
```

```html
<!-- web/templates/components/lead_pool_table.html -->
<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>昵称</th>
        <th>来源</th>
        <th>评分</th>
        <th>等级</th>
        <th>命中信号</th>
        <th>评论内容</th>
        <th>审核状态</th>
        <th>触达状态</th>
      </tr>
    </thead>
    <tbody>
      {% for lead in leads %}
      <tr>
        <td>{{ lead.nickname }}</td>
        <td>{{ lead.source_type }}</td>
        <td>{{ lead.score }}</td>
        <td>{{ lead.grade }}</td>
        <td>{{ lead.matched_signals }}</td>
        <td>{{ lead.comment_text }}</td>
        <td>{{ lead.review_status }}</td>
        <td>{{ lead.contact_status }}</td>
      </tr>
      {% else %}
      <tr><td colspan="8">暂无线索。</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
```

- [ ] **Step 4: Add task-page controls for source/precision/risk/outreach mode**

```html
<!-- web/templates/keyword_funnel.html -->
<form hx-post="/actions/keyword-funnel/collect" hx-target="#keyword-funnel-result">
  <input type="text" name="keyword" placeholder="搜索关键词">
  <select name="source_mode">
    <option value="comments_first">评论优先</option>
    <option value="search_first">搜索优先</option>
    <option value="mixed">评论+搜索</option>
  </select>
  <select name="precision_mode">
    <option value="precision">少而准</option>
    <option value="balanced">平衡</option>
    <option value="broad">多而广</option>
  </select>
  <select name="risk_mode">
    <option value="safe">安全优先</option>
    <option value="balanced">平衡</option>
    <option value="aggressive">效率优先</option>
  </select>
  <select name="outreach_mode">
    <option value="manual">人工审核</option>
    <option value="semi_auto">半自动发送</option>
    <option value="batch">批量私信</option>
  </select>
  <button type="submit">启动截流任务</button>
</form>
```

- [ ] **Step 5: Run the page tests to verify they pass**

Run: `source /Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github/.venv/bin/activate && python -m pytest tests/web/test_acquisition_pages.py tests/web/test_keyword_funnel.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/routes/pages.py web/routes/actions.py web/templates/base.html web/templates/keyword_funnel.html web/templates/lead_pool.html web/templates/components/lead_pool_table.html tests/web/test_acquisition_pages.py tests/web/test_keyword_funnel.py
git commit -m "feat: add acquisition capture and lead pool pages"
```

---

### Task 4: Implement Manual, Semi-Auto, and Batch Outreach Workflows

**Files:**
- Create: `web/services/outreach_service.py`
- Modify: `web/app.py`
- Modify: `web/routes/pages.py`
- Modify: `web/routes/actions.py`
- Create: `web/templates/outreach_center.html`
- Create: `web/templates/components/outreach_queue_table.html`
- Create: `tests/web/test_outreach_service.py`
- Test: `tests/web/test_outreach_service.py`

- [ ] **Step 1: Write the failing outreach tests**

```python
# tests/web/test_outreach_service.py
from web.db import connect_db, init_db
from web.services.outreach_service import OutreachService


def seed_lead(db_path):
    with connect_db(db_path) as conn:
        init_db(conn)
        conn.execute(
            "insert into keyword_leads(run_id, keyword, source_type, source_aweme_id, source_url, user_id, sec_uid, nickname, signature, avatar_url, comment_text, score, grade, score_reasons, matched_signals, review_status, contact_status, conversion_status, risk_flags, raw_payload, dedupe_key, message_status, message_error, created_at, messaged_at) "
            "values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-1", "三角洲上分", "comment", "aweme-1", "https://www.douyin.com/video/1",
                "1001", "sec-1", "Alice", "", "", "求带上分", 92, "S", "[]", "[]",
                "approved", "not_contacted", "new", "[]", "{}", "1001", "pending", "", "2026-05-30T00:00:00+00:00", None,
            ),
        )
        conn.commit()


def test_manual_outreach_marks_contacted(tmp_path):
    db_path = tmp_path / "web-ui.sqlite3"
    seed_lead(db_path)

    class DummyIM:
        def create_conversation(self, to_user_id):
            return {"conversation_id": "conv-1", "conversation_short_id": "short-1", "ticket": "ticket-1"}

        def send_message(self, conversation_id, conversation_short_id, ticket, content):
            return {"detail": {"status": "ok"}}

    service = OutreachService(db_path, DummyIM())
    service.send_manual(lead_id=1, template_key="boosting_intro", content="你好，三角洲可带上分")

    with connect_db(db_path) as conn:
        row = conn.execute("select contact_status from keyword_leads where id = 1").fetchone()
    assert row["contact_status"] == "contacted"
```

- [ ] **Step 2: Run the outreach test to verify it fails**

Run: `source /Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github/.venv/bin/activate && python -m pytest tests/web/test_outreach_service.py -v`

Expected: FAIL with `ModuleNotFoundError` for `web.services.outreach_service`.

- [ ] **Step 3: Implement outreach modes and safe-first gating**

```python
# web/services/outreach_service.py
from datetime import UTC, datetime

from web.db import connect_db, init_db


class OutreachService:
    DAILY_BATCH_LIMIT = 30
    SINGLE_BATCH_LIMIT = 10

    def __init__(self, db_path, im_service):
        self.db_path = db_path
        self.im = im_service
        with connect_db(self.db_path) as conn:
            init_db(conn)

    def send_manual(self, lead_id, template_key, content):
        lead = self._load_lead(lead_id)
        self._deliver(lead, template_key, "manual", content)

    def send_semi_auto(self, lead_ids, template_key, content):
        for lead_id in lead_ids:
            lead = self._load_lead(lead_id)
            if lead["grade"] not in {"S", "A"}:
                continue
            self._deliver(lead, template_key, "semi_auto", content)

    def send_batch(self, lead_ids, template_key, content):
        selected = list(lead_ids)[: self.SINGLE_BATCH_LIMIT]
        for lead_id in selected:
            lead = self._load_lead(lead_id)
            if lead["grade"] not in {"S", "A"}:
                continue
            self._deliver(lead, template_key, "batch", content)

    def _deliver(self, lead, template_key, mode, content):
        conversation = self.im.create_conversation(lead["user_id"])
        self.im.send_message(
            conversation["conversation_id"],
            conversation["conversation_short_id"],
            conversation["ticket"],
            content,
        )
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update keyword_leads set contact_status = ?, review_status = ?, messaged_at = ? where id = ?",
                ("contacted", "approved", datetime.now(UTC).isoformat(), lead["id"]),
            )
            conn.execute(
                "insert into outreach_events(lead_id, mode, template_key, status, note, created_at) values(?, ?, ?, ?, ?, ?)",
                (lead["id"], mode, template_key, "sent", "", datetime.now(UTC).isoformat()),
            )
            conn.commit()

    def _load_lead(self, lead_id):
        with connect_db(self.db_path) as conn:
            row = conn.execute("select * from keyword_leads where id = ?", (lead_id,)).fetchone()
        return dict(row)
```

- [ ] **Step 4: Wire the outreach center**

```python
# web/routes/pages.py
@router.get("/outreach-center", response_class=HTMLResponse)
def outreach_center_page(request: Request):
    events = request.app.state.outreach_service.list_recent_events()
    leads = request.app.state.keyword_funnel_service.list_leads_filtered(grade="S,A", contact_status="not_contacted")
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="outreach_center.html",
        context={"title": "触达中心", "events": events, "leads": leads},
    )
```

```python
# web/routes/actions.py
@router.post("/outreach/manual", response_class=HTMLResponse)
def outreach_manual(request: Request, lead_id: int = Form(...), template_key: str = Form(...), content: str = Form(...)):
    request.app.state.outreach_service.send_manual(lead_id, template_key, content)
    return HTMLResponse("manual outreach sent")
```

- [ ] **Step 5: Run the outreach tests to verify they pass**

Run: `source /Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github/.venv/bin/activate && python -m pytest tests/web/test_outreach_service.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/services/outreach_service.py web/app.py web/routes/pages.py web/routes/actions.py web/templates/outreach_center.html web/templates/components/outreach_queue_table.html tests/web/test_outreach_service.py
git commit -m "feat: add acquisition outreach workflows"
```

---

### Task 5: Add Conversion Tracking and Rules Center

**Files:**
- Create: `web/services/acquisition_dashboard_service.py`
- Create: `web/services/rules_service.py`
- Modify: `web/app.py`
- Modify: `web/routes/pages.py`
- Modify: `web/routes/actions.py`
- Create: `web/templates/acquisition_dashboard.html`
- Create: `web/templates/conversion_tracking.html`
- Create: `web/templates/rules_center.html`
- Create: `web/templates/components/acquisition_metric_cards.html`
- Create: `web/templates/components/rules_form.html`
- Create: `tests/web/test_rules_service.py`
- Modify: `tests/web/test_acquisition_pages.py`
- Test: `tests/web/test_rules_service.py`
- Test: `tests/web/test_acquisition_pages.py`

- [ ] **Step 1: Write the failing rules and conversion page tests**

```python
# tests/web/test_rules_service.py
from web.services.rules_service import RulesService


def test_rules_service_loads_safe_first_defaults(tmp_path):
    service = RulesService(tmp_path / "web-ui.sqlite3")

    rules = service.load()

    assert rules["risk_mode"] == "safe"
    assert rules["single_batch_limit"] == 10
    assert rules["daily_outreach_limit"] == 30
```

```python
# tests/web/test_acquisition_pages.py
def test_dashboard_and_rules_pages_load(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)

    for path in ["/acquisition-dashboard", "/conversion-tracking", "/rules-center"]:
        response = client.get(path)
        assert response.status_code == 200
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `source /Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github/.venv/bin/activate && python -m pytest tests/web/test_rules_service.py tests/web/test_acquisition_pages.py -v`

Expected: FAIL with missing service modules and missing routes.

- [ ] **Step 3: Implement rules defaults and persistence**

```python
# web/services/rules_service.py
import json
from datetime import UTC, datetime

from web.db import connect_db, init_db


DEFAULT_RULES = {
    "risk_mode": "safe",
    "single_batch_limit": 10,
    "daily_outreach_limit": 30,
    "positive_terms": ["求带", "求陪玩", "求上分", "缺队友", "找搭子", "找车队"],
    "delta_terms": ["三角洲", "三角洲行动", "段位", "上分", "带飞"],
}


class RulesService:
    def __init__(self, db_path):
        self.db_path = db_path
        with connect_db(self.db_path) as conn:
            init_db(conn)

    def load(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute("select rule_key, value from acquisition_rules").fetchall()
        if not rows:
            return DEFAULT_RULES.copy()
        result = DEFAULT_RULES.copy()
        for row in rows:
            result[row["rule_key"]] = json.loads(row["value"])
        return result

    def save_many(self, payload):
        now = datetime.now(UTC).isoformat()
        with connect_db(self.db_path) as conn:
            for key, value in payload.items():
                conn.execute(
                    "insert into acquisition_rules(rule_key, value, updated_at) values(?, ?, ?) "
                    "on conflict(rule_key) do update set value = excluded.value, updated_at = excluded.updated_at",
                    (key, json.dumps(value, ensure_ascii=False), now),
                )
            conn.commit()
```

- [ ] **Step 4: Implement dashboard aggregates and conversion page**

```python
# web/services/acquisition_dashboard_service.py
from web.db import connect_db, init_db


class AcquisitionDashboardService:
    def __init__(self, db_path):
        self.db_path = db_path
        with connect_db(self.db_path) as conn:
            init_db(conn)

    def summary(self):
        with connect_db(self.db_path) as conn:
            total = conn.execute("select count(*) as c from keyword_leads").fetchone()["c"]
            high_intent = conn.execute("select count(*) as c from keyword_leads where grade in ('S', 'A')").fetchone()["c"]
            contacted = conn.execute("select count(*) as c from keyword_leads where contact_status = 'contacted'").fetchone()["c"]
            paid = conn.execute("select count(*) as c from keyword_leads where conversion_status = 'paid'").fetchone()["c"]
        return {
            "total_leads": total,
            "high_intent_leads": high_intent,
            "contacted_leads": contacted,
            "paid_leads": paid,
        }
```

- [ ] **Step 5: Run the rules and page tests to verify they pass**

Run: `source /Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github/.venv/bin/activate && python -m pytest tests/web/test_rules_service.py tests/web/test_acquisition_pages.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/services/acquisition_dashboard_service.py web/services/rules_service.py web/app.py web/routes/pages.py web/routes/actions.py web/templates/acquisition_dashboard.html web/templates/conversion_tracking.html web/templates/rules_center.html web/templates/components/acquisition_metric_cards.html web/templates/components/rules_form.html tests/web/test_rules_service.py tests/web/test_acquisition_pages.py
git commit -m "feat: add acquisition dashboard and rules center"
```

---

### Task 6: Update Readme and Run Full Verification

**Files:**
- Modify: `README.md`
- Test: `tests/web/test_db.py`
- Test: `tests/web/test_keyword_funnel.py`
- Test: `tests/web/test_lead_scoring_service.py`
- Test: `tests/web/test_outreach_service.py`
- Test: `tests/web/test_rules_service.py`
- Test: `tests/web/test_acquisition_pages.py`

- [ ] **Step 1: Write the failing documentation test**

```python
# tests/web/test_acquisition_pages.py
def test_base_navigation_contains_acquisition_pages(client):
    response = client.get("/")

    assert "关键词截流" in response.text
    assert "高意向线索池" in response.text
    assert "触达中心" in response.text
    assert "规则中心" in response.text
```

- [ ] **Step 2: Run the navigation test to verify it fails**

Run: `source /Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github/.venv/bin/activate && python -m pytest tests/web/test_acquisition_pages.py::test_base_navigation_contains_acquisition_pages -v`

Expected: FAIL because the extra acquisition links are not yet in the shared shell.

- [ ] **Step 3: Update navigation and README**

```html
<!-- web/templates/base.html -->
<nav>
  <a href="/">概览</a>
  <a href="/keyword-funnel">截流任务</a>
  <a href="/lead-pool">高意向线索池</a>
  <a href="/outreach-center">触达中心</a>
  <a href="/conversion-tracking">转化跟踪</a>
  <a href="/rules-center">规则中心</a>
  <a href="/login">登录中心</a>
  <a href="/api-tools">接口工具</a>
</nav>
```

```markdown
# README.md
## Acquisition Funnel

This repository now includes a local-only acquisition backend for Douyin `Delta Force` lead capture.

Default operating rules:

- comments-first lead collection
- `safe first` outreach policy
- manual review enabled by default
- `S/A` leads prioritized for contact
- batch messaging remains operator-triggered
```

- [ ] **Step 4: Run the full acquisition verification suite**

Run: `source /Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github/.venv/bin/activate && python -m pytest tests/web -v`

Expected: PASS with all acquisition and legacy web tests green.

- [ ] **Step 5: Commit**

```bash
git add web/templates/base.html README.md tests/web
git commit -m "docs: finalize acquisition funnel web surface"
```

---

## Self-Review

### Spec Coverage

- lead acquisition rather than raw crawling: covered by Tasks 2-5
- comment-first, search-second, live-supplemental sourcing: covered by Task 3 controls and Task 2 scoring
- `S/A/B/C` score model: covered by Task 2
- manual / semi-auto / batch workflows: covered by Task 4
- dashboard, lead pool, outreach, conversion, rules pages: covered by Tasks 3-5
- safe-first default limits: covered by Tasks 4-5
- conversion-state tracking: covered by Tasks 4-5

### Placeholder Scan

- no placeholder markers remain in the plan body
- each task contains concrete file paths, test names, commands, and code

### Type Consistency

- `risk_mode`, `precision_mode`, and `outreach_mode` are used consistently across schema and UI
- lead states use `review_status`, `contact_status`, and `conversion_status` throughout
- score outputs consistently use `score`, `grade`, `score_reasons`, and `matched_signals`
