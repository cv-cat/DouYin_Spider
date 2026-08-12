"""路由共享工具。"""
from fastapi import HTTPException

from webapp.backend import deps


def active_auth():
    """返回活跃账号 auth,无则抛 400。"""
    auth = deps.get_account_manager().get_active_auth()
    if auth is None:
        raise HTTPException(400, "没有活跃账号,请先在「账号」页登录并切换")
    return auth
