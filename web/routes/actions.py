from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/actions")


@router.post("/login/cookies", response_class=HTMLResponse)
def save_manual_cookie(request: Request, scope: str = Form(...), cookie_str: str = Form(...)):
    result = request.app.state.login_service.save_manual_cookie(scope, cookie_str)
    return HTMLResponse(result["message"])


@router.post("/login/qr", response_class=HTMLResponse)
def start_qr_login(request: Request):
    task_id = request.app.state.login_service.start_qr_login()
    return HTMLResponse(f"QR login task queued: {task_id}")


@router.post("/login/phone/request-code", response_class=HTMLResponse)
def request_phone_code(request: Request, phone_num: str = Form(...)):
    task_id = request.app.state.login_service.start_phone_code_request(phone_num)
    return HTMLResponse(f"Phone code task queued: {task_id}")


@router.post("/login/phone/confirm", response_class=HTMLResponse)
def confirm_phone_login(request: Request, phone_num: str = Form(...), code: str = Form(...)):
    task_id = request.app.state.login_service.finish_phone_login(phone_num, code)
    return HTMLResponse(f"Phone login confirm task queued: {task_id}")


@router.post("/crawl/work", response_class=HTMLResponse)
def crawl_work(request: Request, work_url: str = Form(...)):
    payload = request.app.state.crawl_service.lookup_work(work_url)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/crawl/user-all", response_class=HTMLResponse)
def crawl_user_all(request: Request, user_url: str = Form(...), save_choice: str = Form("all")):
    task_id = request.app.state.crawl_service.queue_user_export(user_url, save_choice)
    return HTMLResponse(f"user export task queued: {task_id}")


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
