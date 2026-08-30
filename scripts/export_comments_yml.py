from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from yaml_comment_format import add_comment_spacing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--aweme-id", required=True)
    parser.add_argument("--source-url", required=True)
    args = parser.parse_args()
    rows = json.loads(Path(args.source).read_text(encoding="utf-8-sig"))
    groups: dict[str, list[dict]] = defaultdict(list)
    tz = timezone(timedelta(hours=8))
    for row in rows:
        timestamp = int(row.get("create_time") or 0)
        region = str(row.get("ip_location") or "未知").strip() or "未知"
        groups[region].append(
            {
                "comment_id": str(row.get("cid") or ""),
                "published_at": datetime.fromtimestamp(timestamp, tz).isoformat()
                if timestamp else "",
                "nickname": str(row.get("nickname") or ""),
                "content": str(row.get("text") or ""),
                "ip_location": region,
                "profile_url": str(row.get("profile_url") or ""),
                "profile_total_likes": row.get("total_favorited", "未知"),
                "profile_follower_count": row.get("follower_count", "未知"),
            }
        )
    for comments in groups.values():
        comments.sort(key=lambda row: row["published_at"], reverse=True)
    ordered_regions = sorted(groups, key=lambda key: (-len(groups[key]), key))
    payload = {
        "metadata": {
            "schema": "douyin-comments.v1",
            "aweme_id": args.aweme_id,
            "source_url": args.source_url,
            "comment_level": 1,
            "includes_replies": False,
            "total_comments": len(rows),
            "unique_profiles": len({row.get("sec_uid") for row in rows if row.get("sec_uid")}),
            "generated_at": datetime.now(tz).isoformat(timespec="seconds"),
            "timezone": "Asia/Shanghai",
        },
        "ip_summary": [
            {"ip_location": region, "comment_count": len(groups[region])}
            for region in ordered_regions
        ],
        "comments_by_ip": {region: groups[region] for region in ordered_regions},
    }
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120)
    Path(args.output).write_text(add_comment_spacing(rendered), encoding="utf-8")
    print(json.dumps({"output": str(Path(args.output).resolve()), "comments": len(rows), "regions": len(groups)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
