"""Open a Douyin video and scroll until a previously collected comment is visible."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright


def parse_args():
    parser = argparse.ArgumentParser(
        description="在抖音视频评论区自动滚动并高亮目标评论，浏览器会停留供人工回复。"
    )
    parser.add_argument("result", help="collect_ip_comments.py 生成的 JSON 文件")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--cid", help="要定位的评论 ID")
    target.add_argument("--index", type=int, help="结果中的序号，从 1 开始")
    parser.add_argument("--max-scrolls", type=int, default=300, help="最大滚动次数，默认 300")
    parser.add_argument("--interval", type=float, default=0.8, help="每次滚动等待秒数，默认 0.8")
    return parser.parse_args()


def load_target(path, cid=None, index=None):
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if index is not None:
        if index < 1 or index > len(rows):
            raise ValueError(f"--index 必须在 1 到 {len(rows)} 之间")
        return rows[index - 1]
    for row in rows:
        if str(row.get("cid")) == str(cid):
            return row
    raise ValueError(f"结果文件中找不到评论 ID：{cid}")


def cookie_list(cookie_string):
    cookies = []
    for part in cookie_string.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name:
            cookies.append({"name": name, "value": value, "domain": ".douyin.com", "path": "/"})
    return cookies


async def find_and_highlight(page, nickname, text):
    candidates = page.get_by_text(text, exact=True) if text else page.get_by_text(nickname, exact=True)
    for candidate in await candidates.all():
        try:
            matched = await candidate.evaluate(
                """(node, expected) => {
                    let current = node;
                    for (let depth = 0; current && depth < 10; depth++, current = current.parentElement) {
                        const value = (current.innerText || '').trim();
                        if (value.includes(expected.nickname) && (!expected.text || value.includes(expected.text))) {
                            current.scrollIntoView({block: 'center', behavior: 'instant'});
                            current.style.outline = '5px solid #ff2c55';
                            current.style.outlineOffset = '4px';
                            current.style.backgroundColor = 'rgba(255, 235, 59, 0.20)';
                            current.setAttribute('data-codex-comment-match', 'true');
                            return true;
                        }
                    }
                    return false;
                }""",
                {"nickname": nickname, "text": text},
            )
            if matched:
                return True
        except Exception:
            continue
    return False


async def scroll_comment_areas(page):
    await page.evaluate(
        """() => {
            const nodes = [...document.querySelectorAll('*')].filter((el) => {
                const style = getComputedStyle(el);
                return el.scrollHeight > el.clientHeight + 80 &&
                    ['auto', 'scroll'].includes(style.overflowY) && el.clientHeight > 180;
            });
            const targets = nodes.length ? nodes : [document.scrollingElement];
            for (const el of targets) el.scrollTop += Math.max(400, el.clientHeight * 0.75);
        }"""
    )


async def run(args):
    row = load_target(args.result, args.cid, args.index)
    aweme_id = row.get("aweme_id")
    nickname = row.get("nickname") or ""
    text = row.get("text") or ""
    if not aweme_id or not nickname:
        raise ValueError("目标记录缺少 aweme_id 或 nickname")

    load_dotenv()
    raw_cookie = os.getenv("DY_COOKIES", "").strip().strip("'\"")
    if not raw_cookie:
        raise RuntimeError(".env 中缺少 DY_COOKIES")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1440, "height": 960})
        await context.add_cookies(cookie_list(raw_cookie))
        page = await context.new_page()
        await page.goto(f"https://www.douyin.com/video/{aweme_id}", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        for number in range(args.max_scrolls + 1):
            try:
                found = await find_and_highlight(page, nickname, text)
            except PlaywrightError:
                await page.wait_for_timeout(1500)
                continue
            if found:
                print(json.dumps({
                    "found": True, "cid": row.get("cid"), "nickname": nickname,
                    "text": text or "（图片评论，无文字）", "scrolls": number,
                }, ensure_ascii=False, indent=2))
                print("已用红框高亮目标评论。请在浏览器中手动点击回复；关闭浏览器后命令结束。")
                await page.wait_for_event("close", timeout=0)
                return 0
            try:
                await scroll_comment_areas(page)
            except PlaywrightError:
                # Douyin may replace the page after its initial client-side redirect.
                await page.wait_for_timeout(1500)
                continue
            await page.wait_for_timeout(int(args.interval * 1000))

        print(json.dumps({
            "found": False, "cid": row.get("cid"), "nickname": nickname,
            "reason": "滚动到上限仍未在当前排序中找到；评论可能被折叠、删除或排序发生变化",
        }, ensure_ascii=False, indent=2))
        await page.wait_for_timeout(15000)
        return 2


def main():
    args = parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}")
        raise SystemExit(1)
