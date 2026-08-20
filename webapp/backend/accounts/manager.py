"""账号管理器:多抖音账号、登录流程、活跃会话、校验。

登录流程:
- QR:dyGenerateInitData(匿名) → dyGenerateQRcode → 轮询 dyCheckQrCodeLogin →
  跟随 redirect_url 收集登录 cookies → dyGenerateInitData(cookie_str) 提取签名凭证 → 存盘
- Cookie 粘贴:可选 headless 提取凭证
- 有头:login_grab_ticket 一次性拿全
"""
import asyncio
import base64
import io
import time
import uuid

import requests

from webapp.backend.accounts import store
from webapp.backend.models.schemas import AccountOut

requests.packages.urllib3.disable_warnings()


def _to_account_out(row: dict) -> AccountOut:
    return AccountOut(
        id=row["id"],
        label=row["label"],
        has_pm_credential=bool(row.get("ticket") and row.get("private_key")),
        created_at=row["created_at"],
        last_used_at=row.get("last_used_at"),
        status=row.get("status") or "unknown",
    )


class AccountManager:
    def __init__(self):
        store.init_db()
        self._auths: dict[int, object] = {}  # account_id -> DouyinAuth(内存缓存)
        self._temp: dict[str, dict] = {}     # temp_id -> {auth, token, ts}
        self._load_all()

    # ---------- 内存 auth 重建 ----------
    def _build_auth(self, row: dict):
        from builder.auth import DouyinAuth
        import json
        cookies = json.loads(row["cookies_json"])
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        auth = DouyinAuth()
        auth.perepare_auth(cookie_str, "", "")
        auth.ticket = row.get("ticket") or None
        auth.ts_sign = row.get("ts_sign") or None
        auth.client_cert = row.get("client_cert") or None
        auth.private_key = row.get("private_key") or None
        return auth

    def _load_all(self):
        for row in store.list_accounts():
            try:
                self._auths[row["id"]] = self._build_auth(row)
            except Exception:
                self._auths[row["id"]] = None

    # ---------- 查询 ----------
    def list(self) -> list[AccountOut]:
        return [_to_account_out(r) for r in store.list_accounts()]

    def active_id(self) -> int | None:
        return store.get_active_id()

    def get_active_auth(self):
        aid = store.get_active_id()
        if aid is None:
            return None
        return self._auths.get(aid)

    def require_active(self):
        auth = self.get_active_auth()
        if auth is None:
            raise ValueError("没有活跃账号,请先登录并切换")
        return auth

    # ---------- 增删改 ----------
    def _persist_auth(self, label: str, auth, status: str = "valid") -> int:
        import json
        cookies = auth.cookie if isinstance(auth.cookie, dict) else {}
        aid = store.create_account(
            label=label, cookies=cookies,
            ticket=getattr(auth, "ticket", "") or "",
            ts_sign=getattr(auth, "ts_sign", "") or "",
            client_cert=getattr(auth, "client_cert", "") or "",
            private_key=getattr(auth, "private_key", "") or "",
            status=status,
        )
        self._auths[aid] = auth
        if store.get_active_id() is None:
            store.set_active(aid)
        return aid

    def delete(self, account_id: int):
        store.delete_account(account_id)
        self._auths.pop(account_id, None)
        if store.get_active_id() == account_id:
            # 切到任意一个剩余账号
            rows = store.list_accounts()
            if rows:
                store.set_active(rows[0]["id"])

    def set_active(self, account_id: int):
        if not store.get_account(account_id):
            raise ValueError("账号不存在")
        store.set_active(account_id)

    def patch(self, account_id: int, label: str | None = None):
        fields = {}
        if label is not None:
            fields["label"] = label
        if fields:
            store.update_account(account_id, **fields)

    # ---------- 校验 ----------
    def validate(self, account_id: int) -> AccountOut:
        from dy_apis.douyin_api import DouyinAPI
        auth = self._auths.get(account_id)
        row = store.get_account(account_id)
        if not row:
            raise ValueError("账号不存在")
        status = "valid"
        uid = None
        try:
            uid = DouyinAPI.get_my_uid(auth)
        except Exception:
            status = "invalid"
        store.update_account(account_id, status=status, last_used_at=store._now())
        row = store.get_account(account_id)
        return _to_account_out(row)

    # ---------- Playwright 辅助 ----------
    async def _playwright_auth(self, cookie_str: str = "", need_credential: bool = False,
                               headless: bool = True, timeout: int = 60):
        """打开 Playwright 收集 cookies;need_credential 时从 localStorage 抽取私信签名凭证。
        抽不到凭证不报错,降级为 cookies-only(私信不可用)。不依赖 SDK 的 dyGenerateInitData。"""
        from playwright.async_api import async_playwright
        from builder.auth import DouyinAuth

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=headless, args=["--disable-blink-features=AutomationControlled"])
                context = await browser.new_context()
                if cookie_str:
                    await context.add_cookies([
                        {"name": part.strip().partition("=")[0],
                         "value": part.strip().partition("=")[2],
                         "domain": ".douyin.com", "path": "/"}
                        for part in cookie_str.split(";") if part.strip()
                    ])
                page = await context.new_page()
                await page.goto("https://www.douyin.com/")
                try:
                    await page.wait_for_load_state("load", timeout=15000)
                except Exception:
                    pass
                web_protect = ""
                keys = ""
                # 滚动等待 cookies(msToken/biz_trace_id)生成;需要凭证时同时等 localStorage
                for _ in range(8):
                    await asyncio.sleep(3)
                    try:
                        await page.mouse.wheel(0, 600)
                    except Exception:
                        pass
                    if need_credential:
                        try:
                            keys = await page.evaluate(
                                'localStorage["security-sdk/s_sdk_crypt_sdk"]')
                            web_protect = await page.evaluate(
                                'localStorage["security-sdk/s_sdk_sign_data_key/web_protect"]')
                        except Exception:
                            continue
                        if keys and web_protect:
                            break
                    else:
                        names = {c["name"] for c in await context.cookies()}
                        if "msToken" in names and "biz_trace_id" in names:
                            break
                cookies = {c["name"]: c["value"] for c in await context.cookies()}
                await browser.close()
        except Exception as e:
            raise RuntimeError(f"Playwright 启动失败,请确保已安装 chromium: playwright install chromium。详情: {e}")

        # 兜底:cookie 里缺 msToken/biz_trace_id 时补上,避免后续 KeyError
        if "msToken" not in cookies:
            from utils.dy_util import generate_msToken
            cookies["msToken"] = generate_msToken()
        if "biz_trace_id" not in cookies:
            cookies["biz_trace_id"] = uuid.uuid4().hex[:16]

        auth = DouyinAuth()
        auth.cookie = cookies
        auth.cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        auth._ttwid = cookies.get("ttwid", "")
        if web_protect and keys:
            # perepare_auth 会从 web_protect/keys 解出 ticket/ts_sign/client_cert/private_key
            auth.perepare_auth("", web_protect, keys)
            auth.cookie = cookies  # perepare_auth 把 cookie 清空了,恢复
            auth.cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        return auth

    # ---------- QR 登录(浏览器弹窗截图法,绕过 SSO 风控) ----------
    async def qr_start(self) -> dict:
        """在 Playwright 里打开抖音登录弹窗,截取二维码。浏览器自带风控处理。"""
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36")
        page = await context.new_page()
        await page.goto("https://www.douyin.com/")
        try:
            await page.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(2)
        # 点「登录」打开弹窗
        try:
            await page.evaluate('''() => {
                const nodes = Array.from(document.querySelectorAll('button, span, div, a, li'));
                const hit = nodes.find(n => ['登录','登 录'].includes((n.textContent||'').trim()));
                if (hit) hit.click();
            }''')
        except Exception:
            pass
        await asyncio.sleep(3)
        # 尝试切到「扫码登录」tab(弹窗可能默认手机号登录)
        try:
            await page.evaluate('''() => {
                const nodes = Array.from(document.querySelectorAll('button, span, div, a, li, [role="tab"]'));
                const hit = nodes.find(n => (n.textContent||'').includes('扫码') || (n.textContent||'').includes('二维码登录'));
                if (hit) hit.click();
            }''')
        except Exception:
            pass
        await asyncio.sleep(2)
        # 截取二维码:用 JS 找最大的正方形 data:image img(抖音把 QR 编成 data URL),按坐标裁剪
        qr_bytes = None
        try:
            box = await page.evaluate('''() => {
                const imgs = Array.from(document.querySelectorAll('img'));
                const cands = imgs.filter(i => i.src && i.src.startsWith('data:image')
                    && i.width > 100 && i.height > 100 && Math.abs(i.width - i.height) < 25);
                cands.sort((a,b) => b.width*b.height - a.width*a.height);
                if (!cands.length) return null;
                const r = cands[0].getBoundingClientRect();
                return {x: r.x, y: r.y, width: r.width, height: r.height};
            }''')
            if box:
                qr_bytes = await page.screenshot(clip=box)
        except Exception:
            pass
        if not qr_bytes:
            # 兜底:截整个视口
            qr_bytes = await page.screenshot(full_page=False)
        data_url = "data:image/png;base64," + base64.b64encode(qr_bytes).decode()
        temp_id = uuid.uuid4().hex[:12]
        self._temp[temp_id] = {"pw": pw, "browser": browser, "context": context,
                               "page": page, "ts": time.time()}
        return {"temp_id": temp_id, "qr_image": data_url, "token": ""}

    async def qr_poll(self, temp_id: str) -> dict:
        temp = self._temp.get(temp_id)
        if not temp:
            return {"status": "expired", "detail": "二维码已过期,请重新生成"}
        if time.time() - temp["ts"] > 180:
            self._cleanup_qr(temp_id)
            return {"status": "expired", "detail": "二维码超时"}
        page = temp["page"]
        context = temp["context"]
        # 优先检测凭证(登录成功)
        keys = web_protect = ""
        try:
            keys = await page.evaluate('localStorage["security-sdk/s_sdk_crypt_sdk"]')
            web_protect = await page.evaluate('localStorage["security-sdk/s_sdk_sign_data_key/web_protect"]')
        except Exception:
            pass
        try:
            cookies = {c["name"]: c["value"] for c in await context.cookies()}
        except Exception:
            cookies = {}
        if keys and web_protect and "sessionid" in cookies:
            try:
                from builder.auth import DouyinAuth
                auth = DouyinAuth()
                auth.cookie = cookies
                auth.cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
                auth._ttwid = cookies.get("ttwid", "")
                auth.perepare_auth("", web_protect, keys)
                auth.cookie = cookies
                auth.cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
                aid = self._persist_auth("抖音账号", auth, status="valid")
                self._cleanup_qr(temp_id)
                return {"status": "confirmed", "detail": "登录成功", "account_id": aid}
            except Exception as e:
                self._cleanup_qr(temp_id)
                return {"status": "error", "detail": f"登录后处理失败: {e}"}
        # 已有 sessionid 但凭证还没出 → 已扫码待确认
        if "sessionid" in cookies:
            return {"status": "scanned", "detail": "已扫码,请在手机确认"}
        return {"status": "new", "detail": "等待扫码"}

    def _cleanup_qr(self, temp_id: str):
        temp = self._temp.pop(temp_id, None)
        if not temp:
            return
        async def _close():
            try:
                await temp["browser"].close()
            except Exception:
                pass
            try:
                await temp["pw"].stop()
            except Exception:
                pass
        try:
            asyncio.get_event_loop().create_task(_close())
        except Exception:
            pass

    def _collect_login_cookies(self, auth, redirect_url: str) -> dict:
        """跟随 redirect_url 跳转链,收集登录后的完整 cookies。"""
        headers = {
            "accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "referer": "https://www.douyin.com/",
        }
        sess = requests.Session()
        sess.cookies.update(auth.cookie)
        sess.get(redirect_url, headers=headers, allow_redirects=True, verify=False, timeout=20)
        return {c.name: c.value for c in sess.cookies}

    # ---------- Cookie 粘贴登录 ----------
    async def cookie_login(self, cookies: str, label: str, extract_credential: bool = True) -> int:
        from builder.auth import DouyinAuth
        from utils.dy_util import trans_cookies
        cookie_dict = trans_cookies(cookies)
        if extract_credential:
            try:
                auth = await self._playwright_auth(cookie_str=cookies, need_credential=True, timeout=60)
                return self._persist_auth(label, auth, status="valid")
            except Exception as e:
                from loguru import logger
                logger.warning(f"Cookie 登录提取凭证失败,降级为仅 cookies 模式: {e}")
                # 降级为仅 cookies
        auth = DouyinAuth()
        auth.perepare_auth(cookies, "", "")
        return self._persist_auth(label, auth, status="valid")

    # ---------- 有头浏览器登录(本地兜底) ----------
    async def headed_login(self, timeout: int = 180) -> int:
        from dy_apis.login_api import DYLoginApi
        login = DYLoginApi()
        auth = await login.login_grab_ticket(headless=False, timeout=timeout)
        return self._persist_auth("抖音账号", auth, status="valid")
