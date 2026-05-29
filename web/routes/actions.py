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
