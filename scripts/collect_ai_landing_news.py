"""Collect a small, recent, public Douyin search sample about AI adoption.

The script deliberately performs one search page per query and does not fetch
comments, profiles, media, or any account-private data.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Permit running the script directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from builder.auth import DouyinAuth
from dy_apis.douyin_api import DouyinAPI


DEFAULT_QUERIES = ("AI落地", "AI应用", "AI项目", "AI新闻")
FIELDS = (
    "query", "query_hits", "sort_hits", "published_at", "work_id", "title", "author", "likes",
    "comments", "favorites", "shares", "topics", "work_url",
)


def format_time(value):
    try:
        timestamp = int(value)
        if timestamp > 10_000_000_000:
            timestamp //= 1000
        return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return ""


def simplify(query, sort_type, item):
    aweme = item.get("aweme_info") or item.get("aweme_mix_info", {}).get("mix_items", [{}])[0]
    if not aweme:
        return None
    stats = aweme.get("statistics") or {}
    extras = aweme.get("text_extra") or []
    topics = [x.get("hashtag_name") for x in extras if x.get("hashtag_name")]
    work_id = str(aweme.get("aweme_id") or "")
    if not work_id:
        return None
    return {
        "query": query,
        "query_hits": query,
        "sort_hits": sort_type,
        "published_at": format_time(aweme.get("create_time")),
        "work_id": work_id,
        "title": (aweme.get("desc") or "").replace("\n", " ").strip(),
        "author": (aweme.get("author") or {}).get("nickname") or "",
        "likes": int(stats.get("digg_count") or 0),
        "comments": int(stats.get("comment_count") or 0),
        "favorites": int(stats.get("collect_count") or 0),
        "shares": int(stats.get("share_count") or 0),
        "topics": ", ".join(topics),
        "work_url": f"https://www.douyin.com/video/{work_id}",
    }


def main():
    parser = argparse.ArgumentParser(description="Collect a small recent Douyin sample about AI adoption.")
    parser.add_argument("--output-dir", default="datas", help="Directory for JSON and CSV results.")
    parser.add_argument("--days", choices=("1", "7", "180"), default="7", help="Douyin publish-time filter.")
    parser.add_argument("--queries", nargs="*", default=DEFAULT_QUERIES)
    parser.add_argument("--sort-types", nargs="*", choices=("0", "1", "2"), default=("0", "1", "2"), help="0=comprehensive, 1=most liked, 2=newest.")
    parser.add_argument("--request-delay", type=float, default=1.0, help="Seconds to pause between public search requests.")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    cookie_string = os.getenv("DY_COOKIES", "")
    if not cookie_string.strip():
        raise RuntimeError("DY_COOKIES is not configured in .env")
    auth = DouyinAuth()
    auth.perepare_auth(cookie_string)
    api = DouyinAPI()
    rows, by_id, search_counts = [], {}, {}
    for query in args.queries:
        for sort_type in args.sort_types:
            payload = api.search_general_work(auth, query, sort_type=sort_type, publish_time=args.days, offset="0", content_type="0")
            if payload.get("status_code") not in (None, 0):
                raise RuntimeError(f"{query} sort={sort_type} search failed: status_code={payload.get('status_code')}")
            source_items = payload.get("data") or []
            search_counts[f"{query}|sort={sort_type}"] = len(source_items)
            for item in source_items:
                row = simplify(query, sort_type, item)
                if not row:
                    continue
                existing = by_id.get(row["work_id"])
                if existing:
                    query_hits = set(existing["query_hits"].split(", "))
                    query_hits.add(query)
                    existing["query_hits"] = ", ".join(sorted(query_hits))
                    sort_hits = set(existing["sort_hits"].split(", "))
                    sort_hits.add(sort_type)
                    existing["sort_hits"] = ", ".join(sorted(sort_hits))
                else:
                    by_id[row["work_id"]] = row
                    rows.append(row)
            if args.request_delay > 0:
                time.sleep(args.request_delay)

    rows.sort(key=lambda row: row["published_at"], reverse=True)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"douyin_ai_landing_{stamp}.json"
    csv_path = output_dir / f"douyin_ai_landing_{stamp}.csv"
    json_path.write_text(json.dumps({"queries": list(args.queries), "sort_types": list(args.sort_types), "days": args.days, "search_counts": search_counts, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "search_counts": search_counts, "unique_rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
