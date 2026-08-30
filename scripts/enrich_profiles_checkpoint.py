from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import collect_ip_comments as collector
from dy_apis.douyin_api import DouyinAPI


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--interval", type=float, default=0.8)
    parser.add_argument("--save-every", type=int, default=10)
    args = parser.parse_args()
    source = Path(args.source)
    output = Path(args.output)
    rows = json.loads(
        (output if output.exists() else source).read_text(encoding="utf-8-sig")
    )
    auth = collector.build_auth()
    cache: dict[str, dict] = {}
    for row in rows:
        sec_uid = str(row.get("sec_uid") or "")
        if sec_uid and row.get("profile_checked"):
            cache[sec_uid] = {
                key: row.get(key)
                for key in (
                    "profile_ip", "gender", "age", "signature",
                    "follower_count", "total_favorited", "profile_error",
                    "profile_checked",
                )
            }
    checked = 0
    for index, row in enumerate(rows, 1):
        sec_uid = str(row.get("sec_uid") or "")
        if row.get("profile_checked"):
            continue
        if sec_uid in cache:
            row.update(cache[sec_uid])
            continue
        try:
            payload = DouyinAPI.get_user_info(auth, row["profile_url"], timeout=12)
            profile = collector.public_profile(payload.get("user") or {})
            profile["profile_checked"] = True
        except Exception as exc:
            profile = {
                "profile_error": str(exc), "profile_checked": True,
                "gender": "未知", "follower_count": "未知",
                "total_favorited": "未知",
            }
        row.update(profile)
        cache[sec_uid] = profile
        checked += 1
        if checked % args.save_every == 0:
            output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"checked": checked, "row": index, "total": len(rows)}, ensure_ascii=False), flush=True)
        if args.interval:
            time.sleep(args.interval)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"done": True, "checked": checked, "total": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
