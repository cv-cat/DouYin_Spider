"""Reply once to an exact collected Douyin comment after identity verification."""

import json
import os
from pathlib import Path


for name in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(name, None)

from collect_ip_comments import build_auth, ip_text
from dy_apis.douyin_api import DouyinAPI


INPUT = Path("datas/hubei_comments_7665337406014942068_20260828.json")
STATE = Path("datas/comment_reply_state_7665337406014942068_7678747713504445233.json")
CONTENT = "滴滴"


def find_comment(auth, aweme_id: str, cid: str) -> tuple[dict, int, int]:
    url = f"https://www.douyin.com/video/{aweme_id}"
    cursor = "0"
    pages = 0
    scanned = 0
    while True:
        pages += 1
        payload = DouyinAPI.get_work_out_comment(auth, url, cursor)
        if payload.get("status_code") not in (None, 0):
            raise RuntimeError(f"Comment API status_code={payload.get('status_code')}")
        comments = payload.get("comments") or []
        for comment in comments:
            scanned += 1
            if str(comment.get("cid") or "") == cid:
                return comment, pages, scanned
        if not comments or payload.get("has_more") != 1:
            raise RuntimeError(f"Comment cid={cid} was not found")
        next_cursor = str(payload.get("cursor", "0"))
        if next_cursor == cursor:
            raise RuntimeError("Comment cursor did not advance")
        cursor = next_cursor


def main() -> None:
    if STATE.exists() and json.loads(STATE.read_text(encoding="utf-8")).get("sent"):
        raise RuntimeError(f"Refusing to repeat a recorded reply: {STATE}")

    target = json.loads(INPUT.read_text(encoding="utf-8"))[0]
    expected = {
        "aweme_id": str(target["aweme_id"]),
        "cid": str(target["cid"]),
        "nickname": target["nickname"],
        "text": target["text"],
        "ip_location": target["ip_location"],
    }
    auth = build_auth()
    live, pages, scanned = find_comment(auth, expected["aweme_id"], expected["cid"])
    actual = {
        "aweme_id": str(live.get("aweme_id") or ""),
        "cid": str(live.get("cid") or ""),
        "nickname": (live.get("user") or {}).get("nickname") or "",
        "text": live.get("text") or "",
        "ip_location": ip_text(live),
    }
    if actual != expected or "湖北" not in actual["ip_location"]:
        raise RuntimeError(f"Live comment identity mismatch: {actual}")

    response = DouyinAPI.publish_comment(
        auth, expected["aweme_id"], CONTENT, reply_id=expected["cid"]
    )
    result = {
        "target": expected,
        "reply": CONTENT,
        "pages": pages,
        "scanned": scanned,
        "sent": response.get("status_code") == 0 and bool(response.get("comment")),
        "reply_cid": str((response.get("comment") or {}).get("cid") or ""),
        "status_code": response.get("status_code"),
    }
    STATE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if not result["sent"]:
        raise RuntimeError("Douyin did not confirm the comment reply")


if __name__ == "__main__":
    main()
