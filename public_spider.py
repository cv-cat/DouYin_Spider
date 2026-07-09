# coding=utf-8
import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from loguru import logger

from builder.auth import DouyinAuth
from dy_apis.douyin_api import DouyinAPI
from utils.cookie_util import get_new_cookies


DEFAULT_USER_URL = (
    "https://www.douyin.com/user/"
    "MS4wLjABAAAAEpmH344CkCw2M58T33Q8TuFpdvJsOyaZcbWxAMc6H03wOVFf1Ow4mPP94TDUS4Us"
)


def normalize_user_url(value: str) -> str:
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://www.douyin.com/user/{value}"


def sec_uid_from_user_url(user_url: str) -> str:
    return user_url.rstrip("/").split("/")[-1].split("?")[0]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, rows: Iterable[Dict]) -> int:
    count = 0
    with path.open("a", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def extract_url_list(url_obj: Dict) -> List[str]:
    if not isinstance(url_obj, dict):
        return []
    urls = url_obj.get("url_list") or []
    return [url for url in urls if url]


def extract_note_image_urls(aweme: Dict) -> List[str]:
    result = []
    for image in aweme.get("images") or []:
        result.extend(extract_url_list(image))
    return result


def extract_comment_image_urls(comment: Dict) -> List[str]:
    result = []
    for image in comment.get("image_list") or []:
        result.extend(extract_url_list(image.get("origin_url") or {}))
    return result


def summarize_user(user_payload: Dict, user_url: str) -> Dict:
    user = user_payload.get("user") or {}
    avatar = user.get("avatar_thumb") or user.get("avatar_300x300") or {}
    return {
        "sec_uid": sec_uid_from_user_url(user_url),
        "uid": user.get("uid"),
        "short_id": user.get("short_id"),
        "unique_id": user.get("unique_id"),
        "nickname": user.get("nickname"),
        "signature": user.get("signature"),
        "avatar": (avatar.get("url_list") or [""])[0],
        "following_count": user.get("following_count"),
        "follower_count": user.get("follower_count"),
        "max_follower_count": user.get("max_follower_count"),
        "total_favorited": user.get("total_favorited"),
        "aweme_count": user.get("aweme_count"),
        "ip_location": user.get("ip_location"),
        "raw_status_code": user_payload.get("status_code"),
    }


def summarize_aweme(aweme: Dict) -> Dict:
    author = aweme.get("author") or {}
    statistics = aweme.get("statistics") or {}
    video = aweme.get("video") or {}
    cover = video.get("cover") or video.get("origin_cover") or {}
    play_addr = video.get("play_addr") or video.get("play_addr_h264") or {}
    aweme_id = aweme.get("aweme_id")
    return {
        "aweme_id": aweme_id,
        "aweme_url": f"https://www.douyin.com/video/{aweme_id}",
        "aweme_type": aweme.get("aweme_type"),
        "desc": aweme.get("desc"),
        "create_time": aweme.get("create_time"),
        "author_sec_uid": author.get("sec_uid"),
        "author_uid": author.get("uid"),
        "author_nickname": author.get("nickname"),
        "digg_count": statistics.get("digg_count"),
        "comment_count": statistics.get("comment_count"),
        "collect_count": statistics.get("collect_count"),
        "share_count": statistics.get("share_count"),
        "cover_url": (cover.get("url_list") or [""])[0],
        "video_urls": extract_url_list(play_addr),
        "note_image_urls": extract_note_image_urls(aweme),
    }


def summarize_comment(comment: Dict, parent_comment_id: str = "0") -> Dict:
    user = comment.get("user") or {}
    avatar = (
        user.get("avatar_medium")
        or user.get("avatar_300x300")
        or user.get("avatar_168x168")
        or user.get("avatar_thumb")
        or {}
    )
    return {
        "comment_id": comment.get("cid"),
        "parent_comment_id": parent_comment_id,
        "aweme_id": comment.get("aweme_id"),
        "content": comment.get("text"),
        "create_time": comment.get("create_time"),
        "ip_location": comment.get("ip_label"),
        "like_count": comment.get("digg_count") or 0,
        "reply_comment_total": comment.get("reply_comment_total") or 0,
        "user_id": user.get("uid"),
        "sec_uid": user.get("sec_uid"),
        "short_user_id": user.get("short_id"),
        "user_unique_id": user.get("unique_id"),
        "nickname": user.get("nickname"),
        "avatar": (avatar.get("url_list") or [""])[0],
        "picture_urls": extract_comment_image_urls(comment),
    }


def read_cookie(args: argparse.Namespace, user_url: str) -> str:
    if args.cookie:
        return args.cookie.strip()

    cookie_path = Path(args.cookie_file)
    if args.refresh_cookie or not cookie_path.exists():
        logger.info("生成匿名 cookie: {}", user_url)
        cookie_info = get_new_cookies(
            url=user_url,
            headless=not args.headed,
            timeout=args.cookie_timeout,
        )
        cookie_str = cookie_info["cookie_str"]
        ensure_dir(cookie_path.parent)
        cookie_path.write_text(cookie_str, encoding="utf-8")
        logger.info("匿名 cookie 已保存: {}", cookie_path)
        return cookie_str

    return cookie_path.read_text(encoding="utf-8").strip()


def build_auth(cookie_str: str) -> DouyinAuth:
    auth = DouyinAuth()
    auth.perepare_auth(cookie_str, "", "")
    if "s_v_web_id" not in auth.cookie:
        raise ValueError("cookie 缺少 s_v_web_id，请使用 --refresh-cookie 重新生成匿名浏览器 cookie")
    return auth


def fetch_aweme_pages(auth: DouyinAuth, user_url: str, max_pages: int, sleep_sec: float) -> List[Dict]:
    max_cursor = "0"
    page = 0
    awemes: List[Dict] = []
    while True:
        if max_pages > 0 and page >= max_pages:
            break
        payload = DouyinAPI.get_user_work_info(auth, user_url, max_cursor)
        items = payload.get("aweme_list") or []
        logger.info("作品页 {}: {} 条", page + 1, len(items))
        awemes.extend(items)
        page += 1
        if payload.get("has_more") != 1 or not items:
            break
        max_cursor = str(payload.get("max_cursor") or "0")
        time.sleep(sleep_sec)
    return awemes


def fetch_comments(
        auth: DouyinAuth,
        aweme_id: str,
        max_comments: int,
        include_replies: bool,
        sleep_sec: float,
) -> List[Dict]:
    video_url = f"https://www.douyin.com/video/{aweme_id}"
    cursor = "0"
    comments: List[Dict] = []
    while True:
        if max_comments > 0 and len(comments) >= max_comments:
            break
        payload = DouyinAPI.get_work_out_comment(auth, video_url, cursor)
        page_comments = payload.get("comments") or []
        if max_comments > 0:
            remain = max_comments - len(comments)
            page_comments = page_comments[:remain]
        comments.extend(page_comments)
        logger.info("作品 {} 评论游标 {}: {} 条", aweme_id, cursor, len(page_comments))
        if payload.get("has_more") != 1 or not page_comments:
            break
        cursor = str(payload.get("cursor") or "0")
        time.sleep(sleep_sec)

    if not include_replies:
        return comments

    all_comments = list(comments)
    for comment in comments:
        if (comment.get("reply_comment_total") or 0) <= 0:
            continue
        try:
            replies = DouyinAPI.get_work_all_inner_comment(auth, comment)
        except Exception as exc:
            logger.warning("二级评论获取失败 cid={} err={}", comment.get("cid"), exc)
            continue
        for reply in replies:
            reply["_parent_comment_id"] = comment.get("cid")
        all_comments.extend(replies)
        time.sleep(sleep_sec)
    return all_comments


def run(args: argparse.Namespace) -> None:
    user_url = normalize_user_url(args.user_url)
    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)
    for file_name in ("user.json", "videos.jsonl", "comments.jsonl", "summary.json"):
        output_file = output_dir / file_name
        if output_file.exists():
            output_file.unlink()

    cookie_str = read_cookie(args, user_url)
    auth = build_auth(cookie_str)

    user_payload = DouyinAPI.get_user_info(auth, user_url)
    user_summary = summarize_user(user_payload, user_url)
    write_json(output_dir / "user.json", user_summary)

    awemes = fetch_aweme_pages(auth, user_url, args.max_pages, args.sleep)
    videos = [summarize_aweme(item) for item in awemes]
    append_jsonl(output_dir / "videos.jsonl", videos)

    total_comments = 0
    comments_with_pictures = 0
    for video in videos:
        comments = fetch_comments(
            auth=auth,
            aweme_id=video["aweme_id"],
            max_comments=args.max_comments_per_video,
            include_replies=args.include_replies,
            sleep_sec=args.sleep,
        )
        rows = [
            summarize_comment(comment, parent_comment_id=comment.get("_parent_comment_id", "0"))
            for comment in comments
        ]
        total_comments += len(rows)
        comments_with_pictures += sum(1 for row in rows if row["picture_urls"])
        append_jsonl(output_dir / "comments.jsonl", rows)
        time.sleep(args.sleep)

    summary = {
        "user_url": user_url,
        "output_dir": str(output_dir),
        "video_count": len(videos),
        "comment_count": total_comments,
        "comments_with_pictures": comments_with_pictures,
    }
    write_json(output_dir / "summary.json", summary)
    logger.info("完成: {}", json.dumps(summary, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="匿名 cookie 公开抖音账号采集入口")
    parser.add_argument("--user-url", default=DEFAULT_USER_URL, help="用户主页 URL 或 sec_uid")
    parser.add_argument("--cookie", default="", help="直接传入匿名/登录 cookie 字符串")
    parser.add_argument("--cookie-file", default="outputs/anonymous_cookie.txt", help="cookie 文件路径")
    parser.add_argument("--refresh-cookie", action="store_true", help="重新打开浏览器生成匿名 cookie")
    parser.add_argument("--headed", action="store_true", help="生成 cookie 时打开可见 Chrome")
    parser.add_argument("--cookie-timeout", type=int, default=30, help="等待 webid 的秒数")
    parser.add_argument("--output-dir", default="outputs/public_spider", help="输出目录")
    parser.add_argument("--max-pages", type=int, default=1, help="作品列表页数，0 表示直到没有更多")
    parser.add_argument("--max-comments-per-video", type=int, default=20, help="每个作品一级评论数，0 表示直到没有更多")
    parser.add_argument("--include-replies", action="store_true", help="同时抓取二级评论")
    parser.add_argument("--sleep", type=float, default=1.0, help="接口间隔秒数")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
