from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from dotenv import load_dotenv
from playwright.async_api import async_playwright


SENSITIVE_QUERY_KEYS = {"a_bogus", "msToken", "webid", "verifyFp", "fp"}


def parse_cookies(raw: str) -> list[dict[str, str]]:
    cookies = []
    for part in raw.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name:
            cookies.append({"name": name, "value": value, "domain": ".douyin.com", "path": "/"})
    return cookies


async def main() -> int:
    parser = argparse.ArgumentParser(description="监听抖音网页自身发出的评论列表请求")
    parser.add_argument("url")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=30)
    parser.add_argument("--aweme-id", default="", help="只保留指定作品 ID 的评论请求")
    parser.add_argument("--select-latest", action="store_true", help="尝试在评论区选择最新排序")
    args = parser.parse_args()

    load_dotenv()
    raw_cookie = os.getenv("DY_COOKIES", "").strip().strip("'\"")
    if not raw_cookie:
        raise RuntimeError(".env 中缺少 DY_COOKIES")

    captured: list[dict] = []
    async with async_playwright() as playwright:
        browser = None
        errors = []
        for channel in ("msedge", "chrome", None):
            try:
                kwargs = {"headless": False}
                if channel:
                    kwargs["channel"] = channel
                browser = await playwright.chromium.launch(**kwargs)
                break
            except Exception as exc:
                errors.append(f"{channel or 'chromium'}: {exc}")
        if browser is None:
            raise RuntimeError("无法启动浏览器：" + " | ".join(errors))

        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        await context.add_cookies(parse_cookies(raw_cookie))
        page = await context.new_page()

        async def on_response(response):
            if "/aweme/v1/web/comment/list/" not in response.url:
                return
            split = urlsplit(response.url)
            query = dict(parse_qsl(split.query, keep_blank_values=True))
            if args.aweme_id and query.get("aweme_id") != args.aweme_id:
                return
            safe_query = {
                key: ("<redacted>" if key in SENSITIVE_QUERY_KEYS else value)
                for key, value in query.items()
            }
            entry = {
                "status": response.status,
                "path": split.path,
                "query": safe_query,
                "request_header_names": sorted(response.request.headers.keys()),
            }
            try:
                payload = await response.json()
                entry["payload"] = payload
            except Exception:
                text = await response.text()
                entry["body_preview"] = text[:500]
            captured.append(entry)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8")

        page.on("response", on_response)
        await page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        if args.select_latest:
            await page.wait_for_timeout(5000)
            date_filter = page.get_by_text("日期筛选", exact=True).last
            if await date_filter.count() and await date_filter.is_visible():
                await date_filter.click()
                await page.wait_for_timeout(1000)
                for label in ("最新", "最新发布", "按时间"):
                    option = page.get_by_text(label, exact=True).last
                    if await option.count() and await option.is_visible():
                        await option.click()
                        await page.wait_for_timeout(3000)
                        break
        for _ in range(max(1, args.wait_seconds // 2)):
            await page.wait_for_timeout(2000)
            await page.mouse.wheel(0, 700)
            if captured and args.aweme_id:
                break
        await context.close()
        await browser.close()

    print(json.dumps({"captured": len(captured), "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if captured else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
