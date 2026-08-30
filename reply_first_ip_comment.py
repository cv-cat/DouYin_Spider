"""Find the first top-level Douyin comment from a target IP region and optionally reply."""

import argparse
import json
import os
import re
import sys

from dotenv import load_dotenv

from builder.auth import DouyinAuth
from dy_apis.douyin_api import DouyinAPI


def parse_args():
    parser = argparse.ArgumentParser(
        description="按评论区顺序查找首条指定 IP 归属地的一级评论；默认只预览，不发送。"
    )
    parser.add_argument("url", help="抖音视频链接（/video/<id> 或含 modal_id）")
    parser.add_argument("--region", default="湖北", help="IP 归属地关键字，默认：湖北")
    parser.add_argument("--reply", help="要回复的内容；仅 --send 时必填")
    parser.add_argument("--send", action="store_true", help="真正发送回复（默认仅预览）")
    parser.add_argument("--list-replies", action="store_true", help="只读列出命中评论下的现有回复")
    parser.add_argument("--max-pages", type=int, default=0, help="最多读取页数；0 表示直到末页")
    return parser.parse_args()


def extract_aweme_id(url):
    match = re.search(r"/video/(\d+)", url) or re.search(r"[?&]modal_id=(\d+)", url)
    if not match:
        raise ValueError("链接中找不到视频 ID，请使用 /video/<数字> 或含 modal_id=<数字> 的链接")
    return match.group(1)


def ip_text(comment):
    values = [
        comment.get("ip_label"),
        comment.get("ip_location"),
        (comment.get("user") or {}).get("ip_location"),
    ]
    return " ".join(str(value) for value in values if value)


def preview(comment):
    user = comment.get("user") or {}
    return {
        "cid": comment.get("cid"),
        "aweme_id": comment.get("aweme_id"),
        "nickname": user.get("nickname"),
        "ip": ip_text(comment),
        "text": comment.get("text"),
    }


def find_first(auth, url, region, max_pages):
    cursor = "0"
    page = 0
    scanned = 0
    while True:
        page += 1
        payload = DouyinAPI.get_work_out_comment(auth, url, cursor)
        if payload.get("status_code") not in (None, 0):
            raise RuntimeError(f"抖音接口返回错误：{payload}")
        comments = payload.get("comments") or []
        for comment in comments:
            scanned += 1
            if region in ip_text(comment):
                return comment, page, scanned
        if not comments or payload.get("has_more") != 1 or (max_pages and page >= max_pages):
            return None, page, scanned
        cursor = str(payload.get("cursor", "0"))


def main():
    args = parse_args()
    if args.send and not args.reply:
        raise ValueError("使用 --send 时必须同时提供 --reply 回复内容")

    load_dotenv()
    cookie = os.getenv("DY_COOKIES", "").strip().strip("'\"")
    if not cookie:
        raise RuntimeError("缺少 DY_COOKIES：请复制 .env.example 为 .env，并填入已登录 www.douyin.com 的 Cookie")

    aweme_id = extract_aweme_id(args.url)
    canonical_url = f"https://www.douyin.com/video/{aweme_id}"
    auth = DouyinAuth()
    auth.perepare_auth(cookie)
    auth.ticket = os.getenv("DY_TICKET") or None
    auth.ts_sign = os.getenv("DY_TS_SIGN") or None
    auth.client_cert = os.getenv("DY_CLIENT_CERT") or None
    auth.private_key = os.getenv("DY_PRIVATE_KEY") or None

    comment, page, scanned = find_first(auth, canonical_url, args.region, args.max_pages)
    if not comment:
        print(json.dumps({"found": False, "region": args.region, "pages": page, "scanned": scanned}, ensure_ascii=False, indent=2))
        return 2

    result = {"found": True, "pages": page, "scanned": scanned, "comment": preview(comment), "sent": False}
    if args.list_replies:
        replies = DouyinAPI.get_work_all_inner_comment(auth, comment)
        result["replies"] = [preview(reply) for reply in replies]
    if args.send:
        response = DouyinAPI.publish_comment(
            auth, comment.get("aweme_id") or aweme_id, args.reply, reply_id=comment["cid"]
        )
        result["response"] = response
        result["sent"] = response.get("status_code") == 0 and bool(response.get("comment"))
        if not result["sent"]:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 3

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, KeyError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
