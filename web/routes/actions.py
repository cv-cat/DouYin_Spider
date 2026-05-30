from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/actions")


@router.post("/login/cookies", response_class=HTMLResponse)
def save_manual_cookie(request: Request, scope: str = Form(...), cookie_str: str = Form(...)):
    result = request.app.state.login_service.save_manual_cookie(scope, cookie_str)
    return HTMLResponse(result["message"])


@router.post("/login/qr", response_class=HTMLResponse)
def start_qr_login(request: Request):
    qr_state = request.app.state.login_service.begin_qr_login()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="components/login_qr_status.html",
        context={"qr_state": qr_state},
    )


@router.post("/login/browser", response_class=HTMLResponse)
def start_browser_login(request: Request):
    browser_state = request.app.state.login_service.begin_browser_login()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="components/login_browser_status.html",
        context={"browser_state": browser_state},
    )


@router.post("/login/browser/poll", response_class=HTMLResponse)
def poll_browser_login(request: Request, session_id: str = Form(...)):
    browser_state = request.app.state.login_service.poll_browser_login(session_id)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="components/login_browser_status.html",
        context={"browser_state": browser_state},
    )


@router.post("/login/browser/confirm", response_class=HTMLResponse)
def confirm_browser_login(request: Request, session_id: str = Form(...)):
    browser_state = request.app.state.login_service.confirm_browser_login(session_id)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="components/login_browser_status.html",
        context={"browser_state": browser_state},
    )


@router.post("/login/qr/poll", response_class=HTMLResponse)
def poll_qr_login(request: Request, session_id: str = Form(...)):
    qr_state = request.app.state.login_service.poll_qr_login(session_id)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="components/login_qr_status.html",
        context={"qr_state": qr_state},
    )


@router.post("/login/phone/request-code", response_class=HTMLResponse)
def request_phone_code(request: Request, phone_num: str = Form(...)):
    phone_state = request.app.state.login_service.request_phone_code(phone_num)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="components/login_phone_status.html",
        context={"phone_num": phone_num, "phone_state": phone_state},
    )


@router.post("/login/phone/confirm", response_class=HTMLResponse)
def confirm_phone_login(request: Request, phone_num: str = Form(...), code: str = Form(...)):
    task_id = request.app.state.login_service.finish_phone_login(phone_num, code)
    return HTMLResponse(f"Phone login confirm task queued: {task_id}")


@router.post("/login/persist", response_class=HTMLResponse)
def persist_login_record(request: Request, scope: str = Form(...)):
    result = request.app.state.login_service.persist_login_record(scope)
    return HTMLResponse(f"<pre>{result}</pre>")


@router.post("/crawl/work", response_class=HTMLResponse)
def crawl_work(request: Request, work_url: str = Form(...)):
    payload = request.app.state.crawl_service.lookup_work(work_url)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/crawl/user-all", response_class=HTMLResponse)
def crawl_user_all(request: Request, user_url: str = Form(...), save_choice: str = Form("all")):
    task_id = request.app.state.crawl_service.queue_user_export(user_url, save_choice)
    return HTMLResponse(f"user export task queued: {task_id}")


@router.post("/crawl/user", response_class=HTMLResponse)
def crawl_user(request: Request, user_url: str = Form(...)):
    payload = request.app.state.crawl_service.lookup_user(user_url)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/crawl/search", response_class=HTMLResponse)
def crawl_search(
    request: Request,
    query: str = Form(...),
    require_num: str = Form(...),
    sort_type: str = Form("0"),
    publish_time: str = Form("0"),
    filter_duration: str = Form(""),
    search_range: str = Form(""),
    content_type: str = Form(""),
):
    payload = request.app.state.crawl_service.search_general(
        query,
        require_num,
        sort_type,
        publish_time,
        filter_duration,
        search_range,
        content_type,
    )
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/crawl/digg", response_class=HTMLResponse)
def crawl_digg(request: Request, aweme_id: str = Form(...), digg_type: str = Form("1")):
    payload = request.app.state.crawl_service.digg(aweme_id, digg_type)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/crawl/comment", response_class=HTMLResponse)
def crawl_comment(
    request: Request,
    aweme_id: str = Form(...),
    content: str = Form(...),
    reply_id: str = Form(""),
):
    payload = request.app.state.crawl_service.publish_comment(aweme_id, content, reply_id)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/crawl/collect", response_class=HTMLResponse)
def crawl_collect(request: Request, aweme_id: str = Form(...), action: str = Form("1")):
    payload = request.app.state.crawl_service.collect_aweme(aweme_id, action)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/crawl/works-export", response_class=HTMLResponse)
def crawl_works_export(
    request: Request,
    works_text: str = Form(...),
    save_choice: str = Form("all"),
    excel_name: str = Form(""),
):
    task_id = request.app.state.crawl_service.queue_works_export(works_text, save_choice, excel_name)
    return HTMLResponse(f"works export task queued: {task_id}")


@router.post("/crawl/search-export", response_class=HTMLResponse)
def crawl_search_export(
    request: Request,
    query: str = Form(...),
    require_num: str = Form(...),
    save_choice: str = Form("all"),
    sort_type: str = Form("0"),
    publish_time: str = Form("0"),
    filter_duration: str = Form(""),
    search_range: str = Form(""),
    content_type: str = Form(""),
    excel_name: str = Form(""),
):
    task_id = request.app.state.crawl_service.queue_search_export(
        query,
        require_num,
        save_choice,
        sort_type,
        publish_time,
        filter_duration,
        search_range,
        content_type,
        excel_name,
    )
    return HTMLResponse(f"search export task queued: {task_id}")


@router.post("/keyword-funnel/collect", response_class=HTMLResponse)
def keyword_funnel_collect(
    request: Request,
    keyword: str = Form(...),
    require_num: str = Form("10"),
    include_comments: str | None = Form(None),
    comment_limit: str = Form("20"),
    source_mode: str = Form("comments_first"),
    precision_mode: str = Form("precision"),
    risk_mode: str = Form("safe"),
    outreach_mode: str = Form("manual"),
):
    payload = request.app.state.keyword_funnel_service.queue_collect(
        keyword,
        require_num,
        include_comments is not None,
        comment_limit,
        source_mode=source_mode,
        precision_mode=precision_mode,
        risk_mode=risk_mode,
        outreach_mode=outreach_mode,
    )
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="components/keyword_action_result.html",
        context={
            "message": f"keyword collect task queued: run_id={payload['run_id']} task_id={payload['task_id']}",
            "runs": request.app.state.keyword_funnel_service.list_runs(),
            "leads": request.app.state.keyword_funnel_service.list_leads(),
        },
    )


@router.post("/keyword-funnel/message", response_class=HTMLResponse)
def keyword_funnel_message(
    request: Request,
    run_id: str = Form(...),
    content: str = Form(...),
    limit: str = Form(""),
):
    payload = request.app.state.keyword_funnel_service.queue_bulk_message(run_id, content, limit)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="components/keyword_action_result.html",
        context={
            "message": f"keyword message task queued: run_id={payload['run_id']} task_id={payload['task_id']}",
            "runs": request.app.state.keyword_funnel_service.list_runs(),
            "leads": request.app.state.keyword_funnel_service.list_leads(run_id),
        },
    )


@router.post("/live/lookup", response_class=HTMLResponse)
def lookup_live_room(request: Request, live_id: str = Form(...)):
    payload = request.app.state.live_service.lookup_room(live_id)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/live/start", response_class=HTMLResponse)
def start_live_listener(request: Request, live_id: str = Form(...)):
    request.app.state.live_service.start_listener(live_id)
    return HTMLResponse(f"live listener started: {live_id}")


@router.post("/live/stop", response_class=HTMLResponse)
def stop_live_listener(request: Request, live_id: str = Form(...)):
    request.app.state.live_service.stop_listener(live_id)
    return HTMLResponse(f"live listener stopped: {live_id}")


@router.post("/live/send-message", response_class=HTMLResponse)
def send_live_message(request: Request, room_id: str = Form(...), content: str = Form(...)):
    payload = request.app.state.live_service.send_room_message(room_id, content)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/live/like", response_class=HTMLResponse)
def like_live_room(request: Request, room_id: str = Form(...), count: str = Form("1")):
    payload = request.app.state.live_service.like_room(room_id, count)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/im/start", response_class=HTMLResponse)
def start_im_receiver(request: Request):
    request.app.state.im_service.start_receiver()
    return HTMLResponse("im receiver started")


@router.post("/im/stop", response_class=HTMLResponse)
def stop_im_receiver(request: Request):
    request.app.state.im_service.stop_receiver()
    return HTMLResponse("im receiver stopped")


@router.post("/im/conversation/create", response_class=HTMLResponse)
def create_im_conversation(request: Request, to_user_id: str = Form(...)):
    payload = request.app.state.im_service.create_conversation(to_user_id)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/im/conversation/detail", response_class=HTMLResponse)
def get_im_conversation_detail(
    request: Request,
    to_user_id: str = Form(...),
    conversation_short_id: str = Form(...),
):
    payload = request.app.state.im_service.get_conversation_detail(to_user_id, conversation_short_id)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/im/send", response_class=HTMLResponse)
def send_im_message(
    request: Request,
    conversation_id: str = Form(...),
    conversation_short_id: str = Form(...),
    ticket: str = Form(...),
    content: str = Form(...),
):
    payload = request.app.state.im_service.send_message(conversation_id, conversation_short_id, ticket, content)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/settings", response_class=HTMLResponse)
def save_settings(
    request: Request,
    media_dir: str = Form(...),
    excel_dir: str = Form(...),
    port: int = Form(...),
):
    request.app.state.settings_service.save_many(
        {"media_dir": media_dir, "excel_dir": excel_dir, "port": port}
    )
    return HTMLResponse("settings saved; restart app to apply port change")


@router.post("/toolbox/crawl", response_class=HTMLResponse)
async def toolbox_crawl(request: Request):
    form = dict(await request.form())
    operation = form.pop("operation")
    payload = {key: value for key, value in form.items() if value != ""}
    result = request.app.state.crawl_service.invoke(operation, payload)
    return HTMLResponse(f"<pre>{result}</pre>")


@router.post("/toolbox/live", response_class=HTMLResponse)
async def toolbox_live(request: Request):
    form = dict(await request.form())
    operation = form.pop("operation")
    payload = {key: value for key, value in form.items() if value != ""}
    result = request.app.state.live_service.invoke(operation, payload)
    return HTMLResponse(f"<pre>{result}</pre>")
