"""Send one private message to the first two users in a collected result."""

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


INPUT = Path("datas/hubei_comments_7665337406014942068_20260828.json")
STATE = Path("datas/didi_send_state_7665337406014942068_20260828.json")
CONTENT = "滴滴"


def main() -> None:
    if STATE.exists():
        previous = json.loads(STATE.read_text(encoding="utf-8"))
        if any(item.get("sent") for item in previous.get("results", [])):
            raise RuntimeError(f"Refusing to repeat a recorded send: {STATE}")

    rows = json.loads(INPUT.read_text(encoding="utf-8"))
    if len(rows) < 2:
        raise RuntimeError("The collected result contains fewer than two users")

    auth = build_auth()
    results = []
    for rank, row in enumerate(rows[:2], start=1):
        result = {
            "rank": rank,
            "nickname": row["nickname"],
            "uid": str(row["uid"]),
            "sec_uid": row["sec_uid"],
            "profile_url": row["profile_url"],
            "content": CONTENT,
            "sent": False,
        }
        try:
            profile = DouyinAPI.get_user_info(auth, row["profile_url"]).get("user") or {}
            live_uid = str(profile.get("uid") or "")
            live_sec_uid = str(profile.get("sec_uid") or profile.get("sec_user_id") or "")
            if live_uid != result["uid"] or live_sec_uid != result["sec_uid"]:
                raise RuntimeError("Profile identity did not match the collected uid/sec_uid")
            conversation_id, conversation_short_id, ticket = DouyinAPI.create_conversation(
                auth, int(live_uid)
            )
            result["sent"] = DouyinAPI.send_msg(
                auth, conversation_id, conversation_short_id, ticket, CONTENT
            )
            if not result["sent"]:
                result["error"] = "Douyin send API did not return OK"
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        results.append(result)
        STATE.write_text(
            json.dumps({"input": str(INPUT), "results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(json.dumps({"results": results}, ensure_ascii=False))
    if not all(item["sent"] for item in results):
        raise RuntimeError("One or more private messages were not confirmed sent")


if __name__ == "__main__":
    main()
