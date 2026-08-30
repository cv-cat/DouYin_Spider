"""Read existing replies for the exact target comment without sending anything."""

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

from collect_ip_comments import build_auth
from dy_apis.douyin_api import DouyinAPI
from reply_exact_collected_comment import find_comment


rows = json.loads(
    Path("datas/hubei_comments_7665337406014942068_20260828.json").read_text(encoding="utf-8")
)
target = rows[0]
auth = build_auth()
comment, _, _ = find_comment(auth, str(target["aweme_id"]), str(target["cid"]))
try:
    replies = DouyinAPI.get_work_all_inner_comment(auth, comment)
    reply_error = ""
except Exception as exc:
    replies = []
    reply_error = f"{type(exc).__name__}: {exc}"
print(
    json.dumps(
        {
            "target_cid": str(target["cid"]),
            "reported_reply_count": int(comment.get("reply_comment_total") or 0),
            "reply_list_error": reply_error,
            "replies": [
                {
                    "cid": str(reply.get("cid") or ""),
                    "text": reply.get("text") or "",
                    "nickname": (reply.get("user") or {}).get("nickname") or "",
                    "uid": str((reply.get("user") or {}).get("uid") or ""),
                }
                for reply in replies
            ],
        },
        ensure_ascii=False,
    )
)
