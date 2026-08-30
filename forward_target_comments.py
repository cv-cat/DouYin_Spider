"""Find collected Douyin comments in the web UI and forward them to one account."""

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


COMMENT_ITEM = '[data-e2e="comment-item"]'
COMMENT_LIST = '[data-e2e="comment-list"]'
SHARE_MODAL = '[data-e2e="video-share-container"]'


def parse_args():
    parser = argparse.ArgumentParser(
        description="快速滚动抖音评论区，匹配目标评论并转发给指定账号。默认实际转发。"
    )
    parser.add_argument("video_url", help="抖音视频链接")
    parser.add_argument("targets", help="collect_ip_comments.py 生成的 JSON 文件，最多读取 500 条")
    parser.add_argument("--recipient", default="小余同学", help="转发接收账号，默认：小余同学")
    parser.add_argument("--limit", type=int, default=500, help="本次最多处理目标数，最大 500")
    parser.add_argument("--max-scrolls", type=int, default=5000, help="最大滚动次数")
    parser.add_argument("--scroll-wait", type=float, default=0.2, help="每次快速滚动等待秒数，默认 0.2")
    parser.add_argument("--send-wait", type=float, default=1.5, help="两次转发之间等待秒数，默认 1.5")
    parser.add_argument("--dry-run", action="store_true", help="只匹配和标记，不点击最终分享")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口，便于调试")
    parser.add_argument("--state", default="datas/forwarded_comments.json", help="去重与进度记录文件")
    return parser.parse_args()


def normalize_text(value):
    return re.sub(r"\s+", "", str(value or "")).strip()


def load_targets(path, limit=500):
    if limit < 1 or limit > 500:
        raise ValueError("--limit 必须在 1 到 500 之间")
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("目标文件必须是 JSON 数组")
    result = []
    seen = set()
    for row in rows:
        cid = str(row.get("cid") or "")
        nickname = normalize_text(row.get("nickname"))
        if not cid or not nickname or cid in seen:
            continue
        seen.add(cid)
        result.append({
            "cid": cid,
            "nickname": nickname,
            "text": normalize_text(row.get("text")),
            "raw_text": row.get("text") or "",
        })
        if len(result) >= limit:
            break
    return result


def load_state(path):
    state_path = Path(path)
    if not state_path.exists():
        return {"processed": {}}
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload.setdefault("processed", {})
    return payload


def save_state(path, state):
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(state_path)


def browser_cookies(cookie_string):
    cookies = []
    for part in cookie_string.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name:
            cookies.append({"name": name, "value": value, "domain": ".douyin.com", "path": "/"})
    return cookies


def target_matches(target, item_text):
    value = normalize_text(item_text)
    return target["nickname"] in value and (not target["text"] or target["text"] in value)


async def mark_item(item, cid):
    await item.evaluate(
        """(node, cid) => {
            node.dataset.codexTargetCid = cid;
            node.style.outline = '4px solid #ff2c55';
            node.style.outlineOffset = '2px';
            node.style.background = 'rgba(255, 235, 59, 0.16)';
        }""",
        cid,
    )


async def forward_item(page, item, recipient, dry_run=False):
    await mark_item(item, await item.get_attribute("data-codex-target-cid") or "matched")
    if dry_run:
        return "dry_run"

    share = item.get_by_text("分享", exact=True).first
    await share.click(timeout=5000)
    modal = page.locator(SHARE_MODAL)
    await modal.wait_for(state="visible", timeout=5000)
    search = modal.get_by_placeholder("搜索", exact=True)
    await search.fill(recipient)

    person = modal.get_by_text(recipient, exact=True).first
    await person.wait_for(state="visible", timeout=8000)
    row = person.locator("xpath=ancestor::*[.//button[normalize-space()='分享']][1]")
    button = row.get_by_role("button", name="分享", exact=True)
    await button.click(timeout=5000)

    try:
        await page.get_by_text(re.compile("分享成功|已发送")).first.wait_for(state="visible", timeout=2500)
        status = "sent_confirmed"
    except PlaywrightTimeoutError:
        # Treat an acknowledged click as processed to prevent accidental duplicate sends.
        status = "sent_clicked_unverified"
    try:
        await page.keyboard.press("Escape")
        await modal.wait_for(state="hidden", timeout=2000)
    except PlaywrightError:
        pass
    return status


async def fast_scroll(comment_list, wait_seconds):
    before = await comment_list.evaluate("node => ({top: node.scrollTop, height: node.scrollHeight})")
    await comment_list.evaluate(
        "node => { node.scrollTop += Math.max(node.clientHeight * 0.92, 700); }"
    )
    await asyncio.sleep(wait_seconds)
    after = await comment_list.evaluate("node => ({top: node.scrollTop, height: node.scrollHeight})")
    return before != after


async def run(args):
    targets = load_targets(args.targets, args.limit)
    state = load_state(args.state)
    processed = state["processed"]
    pending = {target["cid"]: target for target in targets if target["cid"] not in processed}
    if not pending:
        print(json.dumps({"ok": True, "message": "没有未处理目标", "targets": len(targets)}, ensure_ascii=False))
        return 0

    load_dotenv()
    raw_cookie = os.getenv("DY_COOKIES", "").strip().strip("'\"")
    if not raw_cookie:
        raise RuntimeError(".env 中缺少 DY_COOKIES")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not args.headed)
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        await context.add_cookies(browser_cookies(raw_cookie))
        page = await context.new_page()
        await page.goto(args.video_url, wait_until="domcontentloaded", timeout=45000)
        comment_list = page.locator(COMMENT_LIST)
        await comment_list.wait_for(state="visible", timeout=20000)

        stagnant = 0
        for scroll_number in range(args.max_scrolls + 1):
            items = await page.locator(COMMENT_ITEM).all()
            visible_records = []
            for item in items:
                try:
                    visible_records.append((item, await item.inner_text(timeout=2000)))
                except PlaywrightError:
                    continue

            matched_this_round = []
            for cid, target in list(pending.items()):
                matches = [(item, text) for item, text in visible_records if target_matches(target, text)]
                if not matches:
                    continue
                if not target["text"] and len(matches) != 1:
                    processed[cid] = {
                        "status": "ambiguous_image_comment", "nickname": target["nickname"],
                        "updated_at": int(time.time()),
                    }
                    pending.pop(cid, None)
                    save_state(args.state, state)
                    continue

                item = matches[0][0]
                await item.set_attribute("data-codex-target-cid", cid)
                try:
                    status = await forward_item(page, item, args.recipient, args.dry_run)
                except PlaywrightError as exc:
                    status = "share_failed"
                    error = str(exc)[:300]
                else:
                    error = ""
                processed[cid] = {
                    "status": status, "nickname": target["nickname"], "text": target["raw_text"],
                    "recipient": args.recipient, "error": error, "updated_at": int(time.time()),
                }
                pending.pop(cid, None)
                matched_this_round.append(cid)
                save_state(args.state, state)
                if not args.dry_run:
                    await asyncio.sleep(args.send_wait)

            if not pending:
                break
            moved = await fast_scroll(comment_list, args.scroll_wait)
            stagnant = 0 if moved else stagnant + 1
            if stagnant >= 10:
                break

        await browser.close()

    summary = {
        "ok": True,
        "targets": len(targets),
        "processed_total": len(processed),
        "remaining": len(pending),
        "sent_or_clicked": sum(
            1 for value in processed.values() if value.get("status", "").startswith("sent_")
        ),
        "dry_run": args.dry_run,
        "state": str(Path(args.state).resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not pending else 2


def main():
    args = parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}")
        raise SystemExit(1)
