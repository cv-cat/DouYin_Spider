"""账号与登录路由。"""
from fastapi import APIRouter, HTTPException

from webapp.backend import deps
from webapp.backend.models.schemas import (
    AccountOut, CookieLoginIn, AccountPatchIn, QrStartOut, QrPollOut, Ok,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _mgr():
    return deps.get_account_manager()


@router.get("", response_model=list[AccountOut])
async def list_accounts():
    return _mgr().list()


@router.get("/active")
async def active():
    aid = _mgr().active_id()
    if aid is None:
        return {"account_id": None, "account": None}
    rows = {a.id: a for a in _mgr().list()}
    return {"account_id": aid, "account": rows.get(aid)}


@router.put("/{account_id}/active", response_model=Ok)
async def set_active(account_id: int):
    try:
        _mgr().set_active(account_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return Ok(msg="已切换")


@router.delete("/{account_id}", response_model=Ok)
async def delete_account(account_id: int):
    _mgr().delete(account_id)
    return Ok(msg="已删除")


@router.patch("/{account_id}", response_model=AccountOut)
async def patch_account(account_id: int, body: AccountPatchIn):
    _mgr().patch(account_id, body.label)
    from webapp.backend.accounts import store
    row = store.get_account(account_id)
    if not row:
        raise HTTPException(404, "账号不存在")
    from webapp.backend.accounts.manager import _to_account_out
    return _to_account_out(row)


@router.post("/{account_id}/validate", response_model=AccountOut)
async def validate_account(account_id: int):
    try:
        return await deps.get_account_manager().validate(account_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ---------- 登录 ----------
@router.post("/login/qr/start", response_model=QrStartOut)
async def qr_start():
    try:
        return await _mgr().qr_start()
    except Exception as e:
        raise HTTPException(500, f"生成二维码失败: {e}")


@router.get("/login/qr/poll", response_model=QrPollOut)
async def qr_poll(temp_id: str):
    return await _mgr().qr_poll(temp_id)


@router.post("/login/cookie")
async def cookie_login(body: CookieLoginIn):
    try:
        aid = await _mgr().cookie_login(body.cookies, body.label, body.extract_credential)
        return {"account_id": aid}
    except Exception as e:
        raise HTTPException(500, f"Cookie 登录失败: {e}")


@router.post("/login/headed")
async def headed_login(timeout: int = 180):
    try:
        aid = await _mgr().headed_login(timeout=timeout)
        return {"account_id": aid}
    except Exception as e:
        raise HTTPException(500, f"登录失败: {e}")
